# 데모 영상 녹화 하니스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright로 웹 UI를 자동 조작하며 15장면 데모를 단일 연속 webm 영상으로 녹화하는 하니스를 만든다.

**Architecture:** `demo_bench.py`의 `SCENES`를 SSOT로 두고 `--export-scenes`로 `scenes.json` 파생. `web/demo-recorder/`의 TS 하니스가 그 JSON을 읽어, 단일 Playwright 컨텍스트에서 로그인·질문·HITL·캡션을 순차 재생하며 녹화한다. 순수 로직(캡션·계정전환·분기)은 Vitest로 단위 테스트하고, 브라우저 상호작용은 실제 1회 실행으로 검증한다.

**Tech Stack:** Python 3.11(demo_bench export), TypeScript + Playwright(라이브러리) + tsx(실행) + Vitest(테스트)

---

## File Structure

| 파일 | 책임 |
|------|------|
| `backend/scripts/demo_bench.py` (수정) | `--export-scenes` 플래그 추가 — SCENES + users.yaml 조인 → scenes.json |
| `backend/tests/scripts/test_demo_bench_export.py` (생성) | export 순수 함수 단위 테스트 |
| `web/package.json` (수정) | playwright·tsx devDep + `record:demo` 스크립트 |
| `web/demo-recorder/lib/types.ts` (생성) | `Scene` 타입 정의 |
| `web/demo-recorder/captions.ts` (생성) | kind→설명 매핑 + 캡션 문자열 생성 (순수) |
| `web/demo-recorder/lib/flow.ts` (생성) | `needsRelogin`·`interactionFor` (순수 분기 로직) |
| `web/demo-recorder/lib/overlay.ts` (생성) | 캡션 DOM 주입·fade |
| `web/demo-recorder/lib/auth.ts` (생성) | 로그인/로그아웃·계정 전환 |
| `web/demo-recorder/lib/chat.ts` (생성) | 질문 타이핑·전송·응답완료 대기 |
| `web/demo-recorder/lib/hitl.ts` (생성) | JUSTIFY 사유입력·승인, clarify 옵션선택 |
| `web/demo-recorder/record-demo.ts` (생성) | 오케스트레이터(진입점) |
| `web/demo-recorder/captions.test.ts` (생성) | captions 단위 테스트 |
| `web/demo-recorder/lib/flow.test.ts` (생성) | flow 단위 테스트 |

**TDD 적용 범위**: Task 1(Python export), Task 4(captions), Task 5(flow)는 순수 로직 → TDD. Task 6~10(브라우저 상호작용)은 실 브라우저·LLM 통합이라 단위 테스트 부적합 → 완전한 구현 코드를 제공하고 Task 11의 실제 실행으로 검증.

---

### Task 1: SCENES export 플래그 (Python, SSOT 파생)

**Files:**
- Modify: `backend/scripts/demo_bench.py`
- Test: `backend/tests/scripts/test_demo_bench_export.py`

`demo_bench.py`에 순수 함수 `_load_user_map`·`_build_scene_export`와 `--export-scenes` CLI 분기를 추가한다. export는 서버 없이 동작(파싱만).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/scripts/test_demo_bench_export.py`:

```python
from scripts.demo_bench import SCENES, CREDENTIALS, _build_scene_export


def test_build_scene_export_shape():
    user_map = {
        "daesu": {"display_name": "오대수", "dept": "인사"},
        "admin": {"display_name": "이우진", "dept": None},
        "mido": {"display_name": "미도", "dept": "제품"},
        "joohwan": {"display_name": "노주환", "dept": "개발"},
    }
    rows = _build_scene_export(SCENES, CREDENTIALS, user_map)

    assert len(rows) == len(SCENES)

    first = rows[0]
    assert first == {
        "id": "01",
        "account": "daesu",
        "password": "daesu123",
        "display_name": "오대수",
        "dept": "인사",
        "question": "Friday, 너는 무슨 일을 도와줄 수 있어?",
        "kind": "capability",
        "resume_text": None,
    }

    # admin은 부서 없음 → dept None
    admin_row = next(r for r in rows if r["account"] == "admin")
    assert admin_row["dept"] is None
    assert admin_row["display_name"] == "이우진"

    # JUSTIFY 장면은 resume_text 보존
    scene06 = next(r for r in rows if r["id"] == "06")
    assert scene06["resume_text"] == "감사 대비 인사 데이터 확인 목적입니다."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_demo_bench_export.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_scene_export'`

- [ ] **Step 3: Write minimal implementation**

In `backend/scripts/demo_bench.py`, add after the `CREDENTIALS` dict (around line 51):

```python
def _load_user_map(path: str = "config/users.yaml") -> dict[str, dict]:
    """users.yaml → {username: {display_name, dept}}. dept는 departments[0] or None."""
    import yaml
    users = yaml.safe_load(Path(path).read_text())["users"]
    out: dict[str, dict] = {}
    for u in users:
        depts = u.get("departments") or []
        out[u["username"]] = {
            "display_name": u.get("display_name", u["username"]),
            "dept": depts[0] if depts else None,
        }
    return out


def _build_scene_export(scenes, credentials, user_map) -> list[dict]:
    """SCENES 튜플 + 자격증명 + 사용자맵 → scenes.json용 dict 리스트."""
    rows: list[dict] = []
    for sid_id, account, question, kind, resume_text in scenes:
        info = user_map.get(account, {"display_name": account, "dept": None})
        rows.append({
            "id": sid_id,
            "account": account,
            "password": credentials[account],
            "display_name": info["display_name"],
            "dept": info["dept"],
            "question": question,
            "kind": kind,
            "resume_text": resume_text,
        })
    return rows


def _export_scenes(out_path: Path) -> None:
    user_map = _load_user_map()
    rows = _build_scene_export(SCENES, CREDENTIALS, user_map)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"[export-scenes] {len(rows)}장면 → {out_path}")
```

Then in `main()`, add the arg and an early-return branch. After the existing `ap.add_argument("--no-reset", ...)` line (line 155), add:

```python
    ap.add_argument("--export-scenes", default=None,
                    help="SCENES를 JSON으로 내보내고 종료(벤치 실행 안 함)")
```

And immediately after `args = ap.parse_args()` (line 156), add:

```python
    if args.export_scenes:
        _export_scenes(Path(args.export_scenes))
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_demo_bench_export.py -v`
Expected: PASS (3 assertions in 1 test)

- [ ] **Step 5: Verify the CLI export works end-to-end**

Run: `cd backend && .venv/bin/python -m scripts.demo_bench --export-scenes /tmp/scenes.json && cat /tmp/scenes.json | head -20`
Expected: `[export-scenes] 15장면 → /tmp/scenes.json` and JSON with 15 objects.

- [ ] **Step 6: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add backend/scripts/demo_bench.py backend/tests/scripts/test_demo_bench_export.py
git commit -m "feat(demo): demo_bench --export-scenes로 SCENES를 JSON 파생

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: web/demo-recorder 스캐폴드 + 의존성

**Files:**
- Modify: `web/package.json`
- Create: `web/demo-recorder/lib/types.ts`

- [ ] **Step 1: Add devDependencies and script**

Run:

```bash
cd /Users/acacian/vscode/company-rag/web
npm install --save-dev playwright tsx
```

Then edit `web/package.json` `scripts` block to add (after the `"test:watch"` line):

```json
    "record:demo": "tsx demo-recorder/record-demo.ts"
```

(Remember to add a comma after the previous entry.)

- [ ] **Step 2: Install Chromium browser binary**

Run: `cd /Users/acacian/vscode/company-rag/web && npx playwright install chromium`
Expected: Chromium downloaded successfully.

- [ ] **Step 3: Create the Scene type**

Create `web/demo-recorder/lib/types.ts`:

```typescript
export type SceneKind =
  | "capability"
  | "permission"
  | "rag"
  | "clarify"
  | "rag_block"
  | "sql_read"
  | "sql_write"
  | "sql_write_deny"
  | "permission_delegate"
  | "audit";

export interface Scene {
  id: string;
  account: string;
  password: string;
  display_name: string;
  dept: string | null;
  question: string;
  kind: SceneKind;
  resume_text: string | null;
}
```

- [ ] **Step 4: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/package.json web/package-lock.json web/demo-recorder/lib/types.ts
git commit -m "chore(demo): web demo-recorder 스캐폴드 + playwright/tsx 의존성

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: captions — 캡션 문자열 생성 (TDD)

**Files:**
- Create: `web/demo-recorder/captions.ts`
- Test: `web/demo-recorder/captions.test.ts`

캡션 포맷: `장면 {id} · {display_name}({dept}) · {설명}`. dept가 null이면 `({dept})` 생략.

- [ ] **Step 1: Write the failing test**

Create `web/demo-recorder/captions.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { captionFor } from "./captions";
import type { Scene } from "./lib/types";

const base: Scene = {
  id: "04", account: "daesu", password: "x",
  display_name: "오대수", dept: "인사",
  question: "보안 관련해서 알려줘", kind: "clarify", resume_text: "사내 문서 검색 (RAG)",
};

describe("captionFor", () => {
  it("includes id, name(dept), and kind description", () => {
    expect(captionFor(base)).toBe("장면 04 · 오대수(인사) · 모호한 질문 → 재질문(HITL)");
  });

  it("omits dept parentheses when dept is null", () => {
    const admin: Scene = { ...base, id: "08", display_name: "이우진", dept: null, kind: "sql_read" };
    expect(captionFor(admin)).toBe("장면 08 · 이우진 · SQL 조회 — 실행 사유 승인(HITL)");
  });

  it("supports per-id override", () => {
    const after: Scene = { ...base, id: "15", account: "mido", display_name: "미도", dept: "제품", kind: "permission" };
    expect(captionFor(after)).toBe("장면 15 · 미도(제품) · 부서 위임 후 — 권한 재확인");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run demo-recorder/captions.test.ts`
Expected: FAIL — cannot find module `./captions`.

- [ ] **Step 3: Write minimal implementation**

Create `web/demo-recorder/captions.ts`:

```typescript
import type { Scene, SceneKind } from "./lib/types";

const KIND_DESC: Record<SceneKind, string> = {
  capability: "AI 도우미 소개 — 무엇을 도와주나",
  permission: "내 권한 조회",
  rag: "사내 문서 검색(RAG)",
  rag_block: "권한 밖 문서 접근 → FGA 차단",
  clarify: "모호한 질문 → 재질문(HITL)",
  sql_read: "SQL 조회 — 실행 사유 승인(HITL)",
  sql_write: "SQL 변경 — 실행 사유 승인(HITL)",
  sql_write_deny: "권한 밖 SQL 변경 → 거부(DENY)",
  permission_delegate: "부서 멤버십 위임 — 사유 승인(HITL)",
  audit: "감사 로그 — 활동 이력 추적",
};

// 서사 흐름상 기본 문구로 부족한 장면만 오버라이드.
const ID_OVERRIDE: Record<string, string> = {
  "10": "법무 문서 열람 권한 부여(HITL)",
  "12": "권한 부여 즉시 반영 — 차단됐던 문서 접근 성공",
  "13": "부서 위임 전 — 권한 확인(before)",
  "15": "부서 위임 후 — 권한 재확인",
};

export function captionFor(scene: Scene): string {
  const who = scene.dept ? `${scene.display_name}(${scene.dept})` : scene.display_name;
  const desc = ID_OVERRIDE[scene.id] ?? KIND_DESC[scene.kind];
  return `장면 ${scene.id} · ${who} · ${desc}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run demo-recorder/captions.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/captions.ts web/demo-recorder/captions.test.ts
git commit -m "feat(demo): 캡션 문자열 생성(captionFor) + 테스트

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: flow — 계정전환·상호작용 분기 (TDD)

**Files:**
- Create: `web/demo-recorder/lib/flow.ts`
- Test: `web/demo-recorder/lib/flow.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/demo-recorder/lib/flow.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { needsRelogin, interactionFor } from "./flow";
import type { Scene } from "./types";

const scene = (over: Partial<Scene>): Scene => ({
  id: "00", account: "daesu", password: "x", display_name: "오대수", dept: "인사",
  question: "q", kind: "rag", resume_text: null, ...over,
});

describe("needsRelogin", () => {
  it("true on first scene (no previous account)", () => {
    expect(needsRelogin(null, "daesu")).toBe(true);
  });
  it("false when same account as previous", () => {
    expect(needsRelogin("daesu", "daesu")).toBe(false);
  });
  it("true when account changes", () => {
    expect(needsRelogin("daesu", "admin")).toBe(true);
  });
});

describe("interactionFor", () => {
  it("clarify when kind is clarify", () => {
    expect(interactionFor(scene({ kind: "clarify", resume_text: "사내 문서 검색 (RAG)" }))).toBe("clarify");
  });
  it("justify when resume_text present and not clarify", () => {
    expect(interactionFor(scene({ kind: "sql_read", resume_text: "사유" }))).toBe("justify");
  });
  it("plain when no resume_text", () => {
    expect(interactionFor(scene({ kind: "rag_block", resume_text: null }))).toBe("plain");
  });
  it("plain for sql_write_deny (no resume)", () => {
    expect(interactionFor(scene({ kind: "sql_write_deny", resume_text: null }))).toBe("plain");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run demo-recorder/lib/flow.test.ts`
Expected: FAIL — cannot find module `./flow`.

- [ ] **Step 3: Write minimal implementation**

Create `web/demo-recorder/lib/flow.ts`:

```typescript
import type { Scene } from "./types";

export type Interaction = "clarify" | "justify" | "plain";

export function needsRelogin(prevAccount: string | null, nextAccount: string): boolean {
  return prevAccount !== nextAccount;
}

export function interactionFor(scene: Scene): Interaction {
  if (scene.kind === "clarify") return "clarify";
  if (scene.resume_text !== null) return "justify";
  return "plain";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run demo-recorder/lib/flow.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/lib/flow.ts web/demo-recorder/lib/flow.test.ts
git commit -m "feat(demo): 계정전환·상호작용 분기 로직(flow) + 테스트

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: overlay — 캡션 DOM 주입 (구현, 실행 검증)

**Files:**
- Create: `web/demo-recorder/lib/overlay.ts`

브라우저 상호작용이라 단위 테스트 없이 완전한 구현을 제공하고 Task 11에서 검증.

- [ ] **Step 1: Write implementation**

Create `web/demo-recorder/lib/overlay.ts`:

```typescript
import type { Page } from "playwright";

const OVERLAY_ID = "demo-caption-overlay";

/** 화면 하단에 캡션 띠를 fade-in으로 표시(이미 있으면 텍스트만 교체). */
export async function showCaption(page: Page, text: string): Promise<void> {
  await page.evaluate(
    ({ id, text }) => {
      let el = document.getElementById(id);
      if (!el) {
        el = document.createElement("div");
        el.id = id;
        Object.assign(el.style, {
          position: "fixed",
          left: "0",
          right: "0",
          bottom: "0",
          padding: "18px 28px",
          background: "rgba(17,17,17,0.82)",
          color: "#fff",
          font: "600 18px/1.4 system-ui, sans-serif",
          textAlign: "center",
          zIndex: "2147483647",
          opacity: "0",
          transition: "opacity 0.4s ease",
          pointerEvents: "none",
        } as CSSStyleDeclaration);
        document.body.appendChild(el);
      }
      el.textContent = text;
      // 강제 reflow 후 fade-in
      void el.offsetHeight;
      el.style.opacity = "1";
    },
    { id: OVERLAY_ID, text },
  );
}

/** 캡션을 fade-out으로 감춤. */
export async function hideCaption(page: Page): Promise<void> {
  await page.evaluate((id) => {
    const el = document.getElementById(id);
    if (el) el.style.opacity = "0";
  }, OVERLAY_ID);
  await page.waitForTimeout(400);
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/lib/overlay.ts
git commit -m "feat(demo): 캡션 오버레이 DOM 주입(overlay)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: auth — 로그인/로그아웃 (구현, 실행 검증)

**Files:**
- Create: `web/demo-recorder/lib/auth.ts`

- [ ] **Step 1: Write implementation**

Create `web/demo-recorder/lib/auth.ts`:

```typescript
import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** baseURL의 로그인 폼에서 username/password로 로그인하고 채팅 화면 진입을 대기. */
export async function login(
  page: Page,
  baseURL: string,
  username: string,
  password: string,
): Promise<void> {
  await page.goto(baseURL);
  await page.locator('input[autocomplete="username"]').fill("");
  await page.locator('input[autocomplete="username"]').type(username, { delay: TYPING_DELAY_MS });
  await page.locator('input[type="password"]').type(password, { delay: TYPING_DELAY_MS });
  await page.locator('button[type="submit"]').click();
  // 채팅 화면의 질문 입력창이 나타날 때까지 대기
  await page.locator("textarea").waitFor({ state: "visible", timeout: 15000 });
}

/** 헤더의 로그아웃 버튼을 눌러 로그인 화면으로 복귀. */
export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.locator('input[autocomplete="username"]').waitFor({ state: "visible", timeout: 10000 });
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/lib/auth.ts
git commit -m "feat(demo): 로그인/로그아웃 자동화(auth)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: chat — 질문 전송·응답완료 대기 (구현, 실행 검증)

**Files:**
- Create: `web/demo-recorder/lib/chat.ts`

응답 완료 = "답변 생성 중…" 인디케이터가 사라지고 입력 textarea가 다시 활성화됨.

- [ ] **Step 1: Write implementation**

Create `web/demo-recorder/lib/chat.ts`:

```typescript
import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** 채팅 입력창에 질문을 타이핑하고 전송. */
export async function askQuestion(page: Page, question: string): Promise<void> {
  const box = page.locator("textarea");
  await box.click();
  await box.type(question, { delay: TYPING_DELAY_MS });
  await page.getByRole("button", { name: "전송" }).click();
}

/**
 * 스트리밍 응답이 끝날 때까지 대기.
 * "답변 생성 중…" 텍스트가 없고 첫 textarea가 비활성(disabled)이 아닐 때 완료로 판단.
 */
export async function waitForAnswer(page: Page, timeoutMs = 60000): Promise<void> {
  await page.waitForFunction(
    () => {
      const loading = Array.from(document.querySelectorAll("*")).some(
        (n) => n.textContent?.trim() === "답변 생성 중…",
      );
      const ta = document.querySelector("textarea") as HTMLTextAreaElement | null;
      const enabled = ta != null && !ta.disabled;
      return !loading && enabled;
    },
    undefined,
    { timeout: timeoutMs, polling: 200 },
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/lib/chat.ts
git commit -m "feat(demo): 질문 전송·응답완료 대기(chat)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: hitl — JUSTIFY·clarify 상호작용 (구현, 실행 검증)

**Files:**
- Create: `web/demo-recorder/lib/hitl.ts`

JUSTIFY: InterruptCard("실행 승인이 필요합니다") 대기 → 사유 textarea(placeholder "실행 사유를 입력하세요")에 입력 → 전송. clarify: 옵션 버튼(label 텍스트) 클릭.

- [ ] **Step 1: Write implementation**

Create `web/demo-recorder/lib/hitl.ts`:

```typescript
import type { Page } from "playwright";

const TYPING_DELAY_MS = 40;

/** JUSTIFY interrupt: 승인 카드가 뜰 때까지 대기 후 사유를 입력하고 전송. */
export async function submitJustification(page: Page, reason: string): Promise<void> {
  await page.getByText("실행 승인이 필요합니다").waitFor({ state: "visible", timeout: 30000 });
  const box = page.locator('textarea[placeholder="실행 사유를 입력하세요"]');
  await box.waitFor({ state: "visible", timeout: 10000 });
  await box.click();
  await box.type(reason, { delay: TYPING_DELAY_MS });
  await page.getByRole("button", { name: "전송" }).click();
}

/** clarify: 주어진 label과 일치하는 옵션 버튼을 클릭. */
export async function selectClarifyOption(page: Page, label: string): Promise<void> {
  const option = page.getByRole("button", { name: label });
  await option.waitFor({ state: "visible", timeout: 30000 });
  await option.click();
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/lib/hitl.ts
git commit -m "feat(demo): JUSTIFY 사유입력·clarify 옵션선택(hitl)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: record-demo — 오케스트레이터 (구현, 실행 검증)

**Files:**
- Create: `web/demo-recorder/record-demo.ts`

- [ ] **Step 1: Write implementation**

Create `web/demo-recorder/record-demo.ts`:

```typescript
import { execFileSync } from "node:child_process";
import { readFileSync, renameSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import type { Scene } from "./lib/types";
import { captionFor } from "./captions";
import { needsRelogin, interactionFor } from "./lib/flow";
import { showCaption, hideCaption } from "./lib/overlay";
import { login, logout } from "./lib/auth";
import { askQuestion, waitForAnswer } from "./lib/chat";
import { submitJustification, selectClarifyOption } from "./lib/hitl";

const HERE = dirname(fileURLToPath(import.meta.url));
const BACKEND = resolve(HERE, "../../backend");
const PY = resolve(BACKEND, ".venv/bin/python");
const SCENES_JSON = resolve(HERE, "scenes.json");
const OUT_DIR = resolve(HERE, "out");

const BASE_URL = process.env.DEMO_BASE_URL ?? "http://localhost:5173";
const READ_PAUSE_MS = 2500;
const VIEWPORT = { width: 1440, height: 900 };

function runPython(args: string[]): void {
  execFileSync(PY, args, { cwd: BACKEND, stdio: "inherit" });
}

async function main(): Promise<void> {
  // 1) SSOT 파생 + 상태 초기화 (서버는 사용자가 미리 기동)
  console.log("▶ scenes.json export");
  runPython(["-m", "scripts.demo_bench", "--export-scenes", SCENES_JSON]);
  console.log("▶ demo_reset");
  runPython(["-m", "scripts.demo_reset"]);

  const scenes: Scene[] = JSON.parse(readFileSync(SCENES_JSON, "utf-8"));
  mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: OUT_DIR, size: VIEWPORT },
  });
  const page = await context.newPage();

  let prevAccount: string | null = null;
  try {
    for (const scene of scenes) {
      console.log(`▶ 장면 ${scene.id} (${scene.account}/${scene.kind})`);
      if (needsRelogin(prevAccount, scene.account)) {
        if (prevAccount !== null) await logout(page);
        await login(page, BASE_URL, scene.account, scene.password);
        prevAccount = scene.account;
      }

      await showCaption(page, captionFor(scene));
      await askQuestion(page, scene.question);

      const interaction = interactionFor(scene);
      if (interaction === "clarify") {
        await selectClarifyOption(page, scene.resume_text!);
        await waitForAnswer(page);
      } else if (interaction === "justify") {
        await waitForAnswer(page); // 승인 카드 등장까지 1차 응답 완료 대기
        await submitJustification(page, scene.resume_text!);
        await waitForAnswer(page);
      } else {
        await waitForAnswer(page);
      }

      await page.waitForTimeout(READ_PAUSE_MS);
      await hideCaption(page);
    }
  } finally {
    await context.close(); // 비디오 flush
    const video = page.video();
    const raw = await video?.path();
    await browser.close();
    if (raw) {
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const final = resolve(OUT_DIR, `demo-${stamp}.webm`);
      renameSync(raw, final);
      console.log(`✔ 영상 저장: ${final}`);
    }
  }
}

main().catch((err) => {
  console.error("✖ 녹화 실패:", err);
  process.exit(1);
});
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/demo-recorder/record-demo.ts
git commit -m "feat(demo): 녹화 오케스트레이터(record-demo)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: scenes.json gitignore

**Files:**
- Modify or Create: `web/.gitignore`

`scenes.json`(생성물)과 `out/`(영상)은 커밋 대상이 아니다.

- [ ] **Step 1: Add ignore entries**

Append to `web/.gitignore` (create if absent):

```
demo-recorder/scenes.json
demo-recorder/out/
```

- [ ] **Step 2: Commit**

```bash
cd /Users/acacian/vscode/company-rag
git add web/.gitignore
git commit -m "chore(demo): scenes.json·out/ gitignore

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 전체 단위 테스트 통과 확인 + 실제 녹화 검증

브라우저 상호작용 코드(Task 5~9)는 여기서 실제 실행으로 검증한다.

- [ ] **Step 1: Run all new unit tests**

Run: `cd backend && .venv/bin/python -m pytest tests/scripts/test_demo_bench_export.py -v`
Expected: PASS

Run: `cd web && npx vitest run demo-recorder/`
Expected: PASS (captions 3 + flow 7)

- [ ] **Step 2: Start servers (수동 전제)**

In separate terminals:
- `cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000` (백엔드)
- `cd web && npm run dev` (프론트, 5173)

Confirm `http://localhost:5173` 로그인 화면이 뜨는지 브라우저로 확인.

- [ ] **Step 3: Run the recorder**

Run: `cd web && npm run record:demo`
Expected:
- `▶ scenes.json export` → 15장면
- `▶ demo_reset` 성공
- 장면 01~15 순차 로그가 흐르고
- `✔ 영상 저장: .../demo-<timestamp>.webm`

- [ ] **Step 4: Watch the video and self-check**

Open the produced webm. Confirm:
- 캡션 띠가 각 장면마다 뜨고 사라진다
- 계정 전환(오대수→이우진→미도→노주환→미도) 로그인이 자연스럽다
- JUSTIFY 장면(06·08·09·10·14)에서 승인 카드 후 사유가 입력된다
- clarify 장면(04)에서 옵션이 선택된다
- 차단/거부 장면(05 rag_block·07 sql_write_deny)에서 거부 응답이 보인다

문제가 있으면 selector/페이싱을 조정(필요 시 프론트에 data-testid 추가는 별도 PR).

- [ ] **Step 5: (선택) PR 생성**

`finishing-a-development-branch` 스킬로 마무리 옵션(merge/PR) 선택.

---

## DoD (CLAUDE.md 기준)

1. **단위 테스트 추가**: Task 1(Python export), Task 3(captions), Task 4(flow). ✓
2. **회귀 점수**: 본 작업은 RAG 그래프/검색 로직을 건드리지 않으므로 `tests/eval/runner.py` 점수에 영향 없음(녹화 도구·SCENES 직렬화만 추가). 변경 없음 명시.
3. **새 의존성/패턴**: playwright·tsx 도입 + 녹화 하니스. 설계는 spec(`2026-06-08-demo-video-recorder-design.md`)에 기록됨. 새 아키텍처 결정 수준이 아니라 도구 추가이므로 ADR 대신 spec/plan로 충분(필요 시 ADR 승격 가능).

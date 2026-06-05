# 채팅 권한 조회 응답 마크다운 가독성 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_format_permission_snapshot()`이 GFM 마크다운 테이블/섹션을 반환하도록 변경해 프론트엔드 `MarkdownRenderer`가 권한 조회 결과를 구조화된 형태로 렌더링하게 한다.

**Architecture:** `manage_permission` 도구의 `_format_permission_snapshot()`만 마크다운으로 변경. `agent.py` `_SYSTEM`에 마크다운 지시 한 줄 추가. 기존 `MarkdownRenderer`(GFM + highlight.js)가 렌더링을 담당하므로 프론트 신규 컴포넌트 없음.

**Tech Stack:** Python 3.11, pytest-asyncio, React + `react-markdown` + `remark-gfm`

---

## 파일 맵

| 파일 | 변경 유형 | 역할 |
|------|----------|------|
| `app/graph/tools/permission_tool.py` | Modify (137-181) | `_format_permission_snapshot()` 마크다운 반환, `_LABEL_EMOJI` dict 추가 |
| `app/graph/nodes/agent.py` | Modify (9-13) | `_SYSTEM` 마크다운 포맷 지시 한 줄 추가 |
| `tests/app/graph/tools/test_permission_tool.py` | Modify | 기존 old-format 어서션 업데이트 + 마크다운 구조 신규 테스트 추가 |
| `web/src/chat/MarkdownRenderer.tsx` | Modify (47-77) | GFM 테이블 `td` max-w 완화 (권한 테이블 2열 레이아웃 대응) |

---

### Task 1: `_format_permission_snapshot()` 마크다운 포맷 신규 테스트 작성

**Files:**
- Modify: `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: 파일 끝에 신규 테스트 2개 추가**

`tests/app/graph/tools/test_permission_tool.py` 파일 맨 아래에 아래 코드 추가:

```python
def test_format_snapshot_markdown_headers():
    """마크다운 섹션 헤더(## 권한 스냅샷, ### 접근 가능 폴더, ### SQL/관리 권한)가 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", [], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용"), ("DDL", "불가")],
    )
    assert "## 권한 스냅샷" in out
    assert "### 접근 가능 폴더" in out
    assert "### SQL/관리 권한" in out


def test_format_snapshot_markdown_capability_table():
    """capability 섹션이 GFM 테이블 형식이고 이모지가 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", ["개발팀"], ["c_level"], [],
        [
            ("SELECT", "즉시 허용"),
            ("대량 SELECT", "사유 기재 후 허용"),
            ("DDL", "불가"),
        ],
    )
    assert "| SELECT | ✅ 즉시 허용 |" in out
    assert "| 대량 SELECT | ⚠️ 사유 기재 후 허용 |" in out
    assert "| DDL | ❌ 불가 |" in out
    # 테이블 헤더 행이 있다
    assert "| 작업 | 허용 여부 |" in out
```

- [ ] **Step 2: 테스트 실행해 FAIL 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py::test_format_snapshot_markdown_headers tests/app/graph/tools/test_permission_tool.py::test_format_snapshot_markdown_capability_table -v
```

예상 결과: 두 테스트 모두 `FAILED` (현재 `_format_permission_snapshot`은 plain text 반환)

---

### Task 2: `_format_permission_snapshot()` 마크다운 구현

**Files:**
- Modify: `app/graph/tools/permission_tool.py` (lines 137-181)

- [ ] **Step 1: `_LABEL_EMOJI` dict와 `_format_permission_snapshot()` 교체**

`permission_tool.py`에서 아래 두 부분을 찾아 교체한다.

**찾을 코드 (136-144행 부근):**
```python
_CAPABILITY_DISPLAY = [
```

**이 줄 바로 위에 추가:**
```python
_LABEL_EMOJI = {
    "즉시 허용": "✅",
    "사유 기재 후 허용": "⚠️",
    "불가": "❌",
}

```

**찾을 코드 (`_format_permission_snapshot` 함수 전체, 164-181행):**
```python
def _format_permission_snapshot(
    uid: str, departments: list, roles: list, folders: list, capabilities: list
) -> str:
    dept_text = ", ".join(departments) if departments else "(없음)"
    role_text = ", ".join(roles) if roles else "(없음)"
    if folders:
        folder_lines = "\n".join(f"  - {f}" for f in folders)
        folder_text = f"{len(folders)}개:\n{folder_lines}"
    else:
        folder_text = "(없음)"
    cap_lines = "\n".join(f"  - {label}: {decision}" for label, decision in capabilities)
    return (
        f"사용자: {uid}\n"
        f"소속 부서: {dept_text}\n"
        f"역할(role): {role_text}\n"
        f"접근 가능 폴더 {folder_text}\n"
        f"SQL/관리 권한:\n{cap_lines}"
    )
```

**교체할 코드:**
```python
def _format_permission_snapshot(
    uid: str, departments: list, roles: list, folders: list, capabilities: list
) -> str:
    dept_text = ", ".join(departments) if departments else "없음"
    role_text = " ".join(f"`{r}`" for r in roles) if roles else "없음"

    lines: list[str] = [
        "## 권한 스냅샷",
        "",
        "| 항목 | 값 |",
        "|------|-----|",
        f"| 사용자 | `{uid}` |",
        f"| 역할 | {role_text} |",
        f"| 소속 부서 | {dept_text} |",
        "",
    ]

    lines.append(f"### 접근 가능 폴더 ({len(folders)}개)" if folders else "### 접근 가능 폴더")
    lines.append("")
    if folders:
        for f in folders:
            lines.append(f"- `{f}`")
    else:
        lines.append("없음")
    lines.append("")

    lines.extend([
        "### SQL/관리 권한",
        "",
        "| 작업 | 허용 여부 |",
        "|------|----------|",
    ])
    for label, decision in capabilities:
        emoji = _LABEL_EMOJI.get(decision, "")
        lines.append(f"| {label} | {emoji} {decision} |".rstrip())

    return "\n".join(lines)
```

- [ ] **Step 2: 신규 테스트 실행해 PASS 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py::test_format_snapshot_markdown_headers tests/app/graph/tools/test_permission_tool.py::test_format_snapshot_markdown_capability_table -v
```

예상 결과: 두 테스트 모두 `PASSED`

---

### Task 3: 기존 테스트 old-format 어서션 업데이트

**Files:**
- Modify: `tests/app/graph/tools/test_permission_tool.py`

`"SQL/관리 권한"` 문자열은 새 헤더 `"### SQL/관리 권한"`의 substring이라 PASS. 실제로 FAIL하는 것은 `"SELECT: 즉시 허용"`, `"DDL: 불가"` 어서션(colon 구분자 → 테이블 행 형식으로 바뀜)뿐이다.

- [ ] **Step 1: `test_format_snapshot_renders_capability_section` 어서션 수정**

파일에서 아래 코드를 찾아:
```python
def test_format_snapshot_renders_capability_section():
    """스냅샷에 'SQL/관리 권한' 섹션과 각 항목이 'label: 결정' 형식으로 렌더링된다."""
    out = _format_permission_snapshot(
        "user-admin", [], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용"), ("DDL", "불가")],
    )
    assert "SQL/관리 권한" in out
    assert "SELECT: 즉시 허용" in out
    assert "DDL: 불가" in out
```

아래로 교체:
```python
def test_format_snapshot_renders_capability_section():
    """스냅샷에 'SQL/관리 권한' 섹션과 각 항목이 GFM 테이블 행으로 렌더링된다."""
    out = _format_permission_snapshot(
        "user-admin", [], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용"), ("DDL", "불가")],
    )
    assert "### SQL/관리 권한" in out
    assert "| SELECT | ✅ 즉시 허용 |" in out
    assert "| DDL | ❌ 불가 |" in out
```

- [ ] **Step 2: 파일 전체 테스트 실행해 모두 PASS 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v
```

예상 결과: 전체 `PASSED` (실패 0)

- [ ] **Step 3: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add app/graph/tools/permission_tool.py tests/app/graph/tools/test_permission_tool.py && git commit -m "feat(permission): 권한 조회 응답 GFM 마크다운 테이블 포맷으로 변경"
```

---

### Task 4: `agent.py` `_SYSTEM` 마크다운 지시 추가

**Files:**
- Modify: `app/graph/nodes/agent.py` (lines 9-13)

- [ ] **Step 1: `_SYSTEM` 상수에 한 줄 추가**

파일에서 아래를 찾아:
```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다."
)
```

아래로 교체:
```python
_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다. "
    "구조화된 정보(목록·비교·수치)는 마크다운 헤더·표·목록을 사용해 정리한다."
)
```

- [ ] **Step 2: 관련 테스트 실행**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/nodes/test_agent.py tests/app/graph/nodes/test_agent_answer.py -v
```

예상 결과: 모두 `PASSED` (`_SYSTEM` 내용 검증 테스트가 없으므로 영향 없음)

- [ ] **Step 3: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add app/graph/nodes/agent.py && git commit -m "feat(agent): 구조화 정보 마크다운 포맷 사용 지시 추가"
```

---

### Task 5: 프론트엔드 `MarkdownRenderer` 테이블 스타일 조정

**Files:**
- Modify: `web/src/chat/MarkdownRenderer.tsx` (lines 47-77)

- [ ] **Step 1: `td` max-w 완화**

`web/src/chat/MarkdownRenderer.tsx`에서 아래를 찾아:
```tsx
  td({ children }) {
    return (
      <td className="px-3 py-2 text-ink align-top max-w-[260px]">{children}</td>
    );
  },
```

아래로 교체:
```tsx
  td({ children }) {
    return (
      <td className="px-3 py-2 text-ink align-top">{children}</td>
    );
  },
```

권한 테이블은 "작업 | 허용 여부" 2열 구조로 좁으므로 `max-w` 제한이 오히려 레이아웃을 깰 수 있다. 제거해도 `overflow-x-auto` 래퍼가 넘침을 처리한다.

- [ ] **Step 2: 프론트엔드 타입 체크**

```bash
cd /Users/acacian/vscode/company-rag/web && npm run typecheck 2>/dev/null || npm run type-check 2>/dev/null || npx tsc --noEmit
```

예상 결과: 에러 없음 (className 변경만이므로)

- [ ] **Step 3: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add web/src/chat/MarkdownRenderer.tsx && git commit -m "style(renderer): 테이블 td max-w 제한 제거"
```

---

### Task 6: 전체 회귀 테스트

- [ ] **Step 1: 백엔드 전체 테스트 실행**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/ -v --tb=short
```

예상 결과: 모두 `PASSED`

실패 시: 실패 테스트 이름과 에러를 확인해 Task 2-4 중 누락된 어서션 수정.

- [ ] **Step 2: eval 회귀 점수 확인 (DoD 요건)**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m tests.eval.runner 2>/dev/null | tail -20
```

예상 결과: 기존 점수 대비 하락 없음. 하락 시 원인 명시 후 PR description에 기록.

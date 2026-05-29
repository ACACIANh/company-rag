# User Team & Role View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인한 유저의 팀(teams)과 역할(roles)을 채팅 페이지 헤더에 배지로 표시한다.

**Architecture:** `users.yaml`의 `teams` 필드를 로그인 시 JWT에 인코딩하고, `AuthUser` TypedDict 및 프론트 타입에 전파한 뒤, `ChatPage` 헤더에 `role: [user]  team: [general]` 형식의 pill 배지로 렌더링한다.

**Tech Stack:** Python 3.11, FastAPI, PyJWT, React 18, TypeScript, Tailwind CSS, Vitest

---

## 파일 변경 맵

| 파일 | 유형 | 역할 |
|------|------|------|
| `shared/auth/base.py` | 수정 | `AuthUser`에 `teams: list[str]` 추가 |
| `shared/auth/jwt_handler.py` | 수정 | `create_token()`에 `teams` 파라미터 추가·인코딩 |
| `app/api/auth.py` | 수정 | `/auth/token`에서 `users.yaml`의 `teams` 읽어 전달 |
| `app/api/deps.py` | 수정 | `get_current_user()`에서 JWT `teams` 추출 |
| `web/src/types.ts` | 수정 | `AuthUser.teams: string[]` 추가 |
| `web/src/auth/AuthContext.test.tsx` | 수정 | 모킹 응답에 `teams` 필드 추가 |
| `web/src/chat/ChatPage.tsx` | 수정 | 헤더 role/team 배지 렌더링 |
| `tests/shared/auth/test_jwt_handler.py` | 수정 | `teams` 관련 테스트 추가·기존 콜 수정 |
| `tests/app/api/test_auth.py` | 수정 | `teams` 반환 검증 테스트 추가 |
| `web/src/chat/ChatPage.test.tsx` | 신규 | 헤더 배지 렌더링 단위 테스트 |

---

## Task 1: shared/auth 레이어 — `AuthUser` + JWT teams 지원

**Files:**
- Modify: `shared/auth/base.py`
- Modify: `shared/auth/jwt_handler.py`
- Modify: `tests/shared/auth/test_jwt_handler.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/auth/test_jwt_handler.py` 끝에 추가:

```python
def test_teams_encoded_and_decoded():
    token = create_token(
        user_id="u1",
        roles=["user"],
        teams=["general"],
        allowed_doc_ids=[],
        secret="s",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="s")
    assert payload["teams"] == ["general"]


def test_empty_teams_encoded():
    token = create_token(
        user_id="u1",
        roles=["admin"],
        teams=[],
        allowed_doc_ids=[],
        secret="s",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="s")
    assert payload["teams"] == []
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/shared/auth/test_jwt_handler.py -v
```

Expected: `FAILED test_teams_encoded_and_decoded — TypeError: create_token() got an unexpected keyword argument 'teams'`

- [ ] **Step 3: `AuthUser`에 `teams` 추가**

`shared/auth/base.py` 전체를 다음으로 교체:

```python
from typing import TypedDict


class AuthUser(TypedDict):
    user_id: str
    roles: list[str]
    teams: list[str]
    allowed_doc_ids: list[str]
```

- [ ] **Step 4: `create_token`에 `teams` 파라미터 추가**

`shared/auth/jwt_handler.py` 전체를 다음으로 교체:

```python
from datetime import datetime, timedelta, timezone

import jwt


def create_token(
    user_id: str,
    roles: list[str],
    teams: list[str],
    allowed_doc_ids: list[str],
    secret: str,
    expire_minutes: int,
) -> str:
    payload = {
        "sub": user_id,
        "roles": roles,
        "teams": teams,
        "allowed_doc_ids": allowed_doc_ids,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
```

- [ ] **Step 5: 기존 테스트 콜 수정**

`tests/shared/auth/test_jwt_handler.py`의 기존 두 함수를 다음으로 교체 (`teams=[]` 추가, 키워드 인자로 통일):

```python
def test_create_and_decode_token():
    token = create_token(
        user_id="user-alice",
        roles=["user"],
        teams=[],
        allowed_doc_ids=["docs/company/policy.md"],
        secret="test-secret",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == "user-alice"
    assert payload["roles"] == ["user"]
    assert payload["teams"] == []
    assert payload["allowed_doc_ids"] == ["docs/company/policy.md"]


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not.a.valid.token", secret="test-secret")


def test_decode_wrong_secret_raises():
    token = create_token(
        user_id="u1",
        roles=["user"],
        teams=[],
        allowed_doc_ids=[],
        secret="secret-a",
        expire_minutes=60,
    )
    with pytest.raises(Exception):
        decode_token(token, secret="secret-b")
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/shared/auth/test_jwt_handler.py -v
```

Expected: 모든 테스트 PASS (5개)

- [ ] **Step 7: 커밋**

```bash
git add shared/auth/base.py shared/auth/jwt_handler.py tests/shared/auth/test_jwt_handler.py
git commit -m "feat(auth): AuthUser·JWT에 teams 필드 추가"
```

---

## Task 2: app API 레이어 — login teams 전달 + get_current_user 추출

**Files:**
- Modify: `app/api/auth.py`
- Modify: `app/api/deps.py`
- Modify: `tests/app/api/test_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/api/test_auth.py` 끝에 추가:

```python
def test_me_returns_teams_for_alice():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "alice", "password": "alice123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "teams" in data
    assert data["teams"] == ["general"]


def test_me_returns_empty_teams_for_admin():
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["teams"] == []
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/app/api/test_auth.py -v
```

Expected: `FAILED test_me_returns_teams_for_alice — KeyError: 'teams'` 또는 AssertionError

- [ ] **Step 3: `app/api/auth.py` 수정 — teams 전달**

`login()` 함수 내 `create_token(...)` 호출 부분을 찾아 다음으로 교체:

```python
    token = create_token(
        user_id=user["user_id"],
        roles=user["roles"],
        teams=user.get("teams", []),
        allowed_doc_ids=user["allowed_doc_ids"],
        secret=_config.jwt_secret,
        expire_minutes=_config.jwt_expire_minutes,
    )
```

- [ ] **Step 4: `app/api/deps.py` 수정 — teams 추출**

`get_current_user()` 함수의 `return AuthUser(...)` 부분을 다음으로 교체:

```python
        return AuthUser(
            user_id=payload["sub"],
            roles=payload["roles"],
            teams=payload.get("teams", []),
            allowed_doc_ids=payload["allowed_doc_ids"],
        )
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/app/api/test_auth.py -v
```

Expected: 모든 테스트 PASS (6개)

- [ ] **Step 6: 전체 백엔드 테스트 이상 없음 확인**

```bash
pytest tests/shared/auth/ tests/app/api/ -v
```

Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add app/api/auth.py app/api/deps.py tests/app/api/test_auth.py
git commit -m "feat(api): /auth/token·/auth/me에 teams 반환 추가"
```

---

## Task 3: 프론트엔드 타입 + AuthContext 테스트 업데이트

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/auth/AuthContext.test.tsx`

- [ ] **Step 1: `web/src/types.ts` 수정 — `teams` 추가**

`AuthUser` 인터페이스를 다음으로 교체:

```typescript
export interface AuthUser {
  user_id: string;
  roles: string[];
  teams: string[];
  allowed_doc_ids: string[];
}
```

- [ ] **Step 2: `AuthContext.test.tsx` 모킹 응답에 `teams` 추가**

파일 내 `/auth/me` 응답 모킹 부분 두 곳을 찾아 `teams` 필드를 추가한다.

첫 번째 (login 테스트, `{ user_id: "u1", roles: ["user"], allowed_doc_ids: ["d1"] }`):
```typescript
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ user_id: "u1", roles: ["user"], teams: [], allowed_doc_ids: ["d1"] }),
          { status: 200 }
        )
      );
```

두 번째 (logout 테스트, `{ user_id: "u1", roles: [], allowed_doc_ids: [] }`):
```typescript
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ user_id: "u1", roles: [], teams: [], allowed_doc_ids: [] }),
        { status: 200 }
      )
    );
```

- [ ] **Step 3: 프론트 테스트 통과 확인**

```bash
cd web && npm test
```

Expected: 전부 PASS

- [ ] **Step 4: 커밋**

```bash
git add web/src/types.ts web/src/auth/AuthContext.test.tsx
git commit -m "feat(web): AuthUser 타입에 teams 필드 추가"
```

---

## Task 4: ChatPage 헤더 배지 렌더링

**Files:**
- Create: `web/src/chat/ChatPage.test.tsx`
- Modify: `web/src/chat/ChatPage.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`web/src/chat/ChatPage.test.tsx` 신규 생성:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatPage } from "./ChatPage";

const mockUseAuth = vi.fn();

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
  getSessions: vi.fn().mockResolvedValue([]),
  getSessionMessages: vi.fn(),
  deleteSession: vi.fn(),
  setOnUnauthorized: vi.fn(),
}));

describe("ChatPage 헤더 배지", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-alice",
        roles: ["user"],
        teams: ["general"],
        allowed_doc_ids: [],
      },
      logout: vi.fn(),
    });
  });

  it("역할 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("user")).toBeInTheDocument();
  });

  it("팀 배지를 렌더링한다", () => {
    render(<ChatPage />);
    expect(screen.getByText("general")).toBeInTheDocument();
  });

  it("teams가 비어 있으면 team: 레이블을 렌더링하지 않는다", () => {
    mockUseAuth.mockReturnValue({
      user: {
        user_id: "user-admin",
        roles: ["admin"],
        teams: [],
        allowed_doc_ids: [],
      },
      logout: vi.fn(),
    });
    render(<ChatPage />);
    expect(screen.queryByText(/^team:$/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 실패 확인**

```bash
cd web && npm test -- --reporter=verbose ChatPage
```

Expected: `FAILED — getByText("user") — unable to find element` (배지 없음)

- [ ] **Step 3: `ChatPage.tsx` 헤더 사용자 영역 수정**

`ChatPage.tsx`의 헤더 우측 영역 (`<div className="flex items-center gap-4">` 블록)을 다음으로 교체:

```tsx
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13px] text-ink-mute font-normal tracking-[-0.39px]">
              {user?.user_id ?? ""}
            </span>
            {user && (
              <>
                <span className="text-[11px] text-ink-mute">role:</span>
                {user.roles.map((r) => (
                  <span
                    key={r}
                    className="bg-primary-muted text-primary-deep text-[10px] font-[400] tracking-[0.1px] rounded-pill px-2 py-[3px] uppercase"
                  >
                    {r}
                  </span>
                ))}
                {user.teams.length > 0 && (
                  <>
                    <span className="text-[11px] text-ink-mute">team:</span>
                    {user.teams.map((t) => (
                      <span
                        key={t}
                        className="bg-primary-muted text-primary-deep text-[10px] font-[400] tracking-[0.1px] rounded-pill px-2 py-[3px] uppercase"
                      >
                        {t}
                      </span>
                    ))}
                  </>
                )}
              </>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="text-[14px] font-normal text-primary hover:text-primary-deep transition-colors"
          >
            로그아웃
          </button>
        </div>
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd web && npm test
```

Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add web/src/chat/ChatPage.tsx web/src/chat/ChatPage.test.tsx
git commit -m "feat(web): 헤더에 role·team 배지 표시"
```

---

## 완료 확인 체크리스트

- [ ] `pytest tests/shared/auth/ tests/app/api/ -v` — 전부 PASS
- [ ] `cd web && npm test` — 전부 PASS
- [ ] alice 계정으로 로그인 시 헤더: `user-alice  role: USER  team: GENERAL  로그아웃`
- [ ] admin 계정으로 로그인 시 헤더: `user-admin  role: ADMIN  role: USER  로그아웃` (team: 없음)
- [ ] restricted 계정으로 로그인 시 헤더: `user-restricted  role: USER  로그아웃` (team: 없음)

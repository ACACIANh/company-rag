# Session Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 왼쪽 토글 사이드바로 세션 목록을 표시하고, 세션 전환 시 메시지 히스토리를 복원하며, 재로그인 후에도 세션 목록이 유지된다.

**Architecture:** `shared/session/` 에 `SessionStore` ABC + `InMemorySessionStore` (dev) 어댑터를 추가한다. `app/api/deps.py` 에 싱글턴을 등록하고 `app/api/sessions.py` 라우터와 `app/api/chat.py` 수정으로 백엔드를 완성한다. 프론트는 `SessionSidebar` 컴포넌트를 신규 추가하고 `ChatPage`에 통합한다.

**Tech Stack:** Python 3.11, FastAPI, LangGraph (MemorySaver 유지), React 18, TypeScript, Tailwind CSS, Vitest + @testing-library/react

---

## File Map

| 파일 | 상태 | 역할 |
|------|------|------|
| `shared/session/__init__.py` | 신규 | 패키지 |
| `shared/session/base.py` | 신규 | `SessionStore` ABC + `SessionMeta` + `StoredMessage` |
| `shared/session/factory.py` | 신규 | `create_session_store(config)` |
| `shared/session/adapters/__init__.py` | 신규 | 패키지 |
| `shared/session/adapters/memory.py` | 신규 | `InMemorySessionStore` |
| `shared/config.py` | 수정 | `session_store_type`, `postgres_dsn` 필드 추가 |
| `app/api/deps.py` | 수정 | `_session_store` 싱글턴 + `get_session_store()` 추가 |
| `app/api/sessions.py` | 신규 | `GET /sessions`, `GET /sessions/{id}/messages`, `DELETE /sessions/{id}` |
| `app/api/chat.py` | 수정 | 응답 후 `session_store` 기록 + `sessions` 라우터 등록 |
| `tests/shared/test_session_store.py` | 신규 | `InMemorySessionStore` 단위 테스트 |
| `tests/app/api/test_sessions.py` | 신규 | sessions API 통합 테스트 |
| `web/src/types.ts` | 수정 | `Session`, `SessionMessage` 타입 추가 |
| `web/src/api/client.ts` | 수정 | `getSessions`, `getSessionMessages`, `deleteSession` 추가 |
| `web/src/chat/SessionSidebar.tsx` | 신규 | 사이드바 컴포넌트 |
| `web/src/chat/SessionSidebar.test.tsx` | 신규 | 렌더링·이벤트 테스트 |
| `web/src/chat/ChatPage.tsx` | 수정 | 사이드바 통합 + 세션 전환 로직 |

---

## Task 1: SessionStore ABC + 데이터 클래스

**Files:**
- Create: `shared/session/__init__.py`
- Create: `shared/session/base.py`
- Create: `shared/session/adapters/__init__.py`

- [ ] **Step 1: 빈 패키지 파일 생성**

```bash
touch shared/session/__init__.py shared/session/adapters/__init__.py
```

- [ ] **Step 2: `shared/session/base.py` 작성**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SessionMeta:
    thread_id: str
    title: str
    created_at: str  # ISO8601


@dataclass
class StoredMessage:
    role: str  # 'user' | 'assistant'
    content: str
    sources: list[str] = field(default_factory=list)


class SessionStore(ABC):
    @abstractmethod
    def create_session(self, thread_id: str, user_id: str, title: str) -> None: ...

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[SessionMeta]: ...

    @abstractmethod
    def get_messages(self, thread_id: str) -> list[StoredMessage]: ...

    @abstractmethod
    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[str]
    ) -> None: ...

    @abstractmethod
    def delete_session(self, thread_id: str, user_id: str) -> None: ...
```

- [ ] **Step 3: Commit**

```bash
git add shared/session/
git commit -m "feat(session): SessionStore ABC + 데이터 클래스 추가"
```

---

## Task 2: InMemorySessionStore + 단위 테스트

**Files:**
- Create: `shared/session/adapters/memory.py`
- Create: `tests/shared/test_session_store.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/shared/test_session_store.py
from shared.session.adapters.memory import InMemorySessionStore


def _store() -> InMemorySessionStore:
    return InMemorySessionStore()


def test_create_and_list():
    store = _store()
    store.create_session("t1", "alice", "첫 번째 질문")
    sessions = store.list_sessions("alice")
    assert len(sessions) == 1
    assert sessions[0].thread_id == "t1"
    assert sessions[0].title == "첫 번째 질문"


def test_list_only_own_sessions():
    store = _store()
    store.create_session("t1", "alice", "앨리스 질문")
    store.create_session("t2", "bob", "밥 질문")
    assert len(store.list_sessions("alice")) == 1
    assert len(store.list_sessions("bob")) == 1


def test_add_and_get_messages():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.add_message("t1", "user", "안녕?", [])
    store.add_message("t1", "assistant", "안녕하세요!", ["doc.md"])
    msgs = store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources == ["doc.md"]


def test_delete_session():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.delete_session("t1", "alice")
    assert store.list_sessions("alice") == []
    assert store.get_messages("t1") == []


def test_delete_does_not_affect_other_user():
    store = _store()
    store.create_session("t1", "alice", "질문")
    store.delete_session("t1", "bob")  # 다른 유저 — 무시해야 함
    assert len(store.list_sessions("alice")) == 1


def test_create_session_idempotent():
    store = _store()
    store.create_session("t1", "alice", "첫 질문")
    store.create_session("t1", "alice", "다른 제목")  # 두 번째 호출은 무시
    assert len(store.list_sessions("alice")) == 1
    assert store.list_sessions("alice")[0].title == "첫 질문"


def test_add_message_to_nonexistent_session_is_noop():
    store = _store()
    store.add_message("ghost", "user", "내용", [])  # 오류 없이 무시
    assert store.get_messages("ghost") == []
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/shared/test_session_store.py -v
```

Expected: `ModuleNotFoundError` 또는 `ImportError`

- [ ] **Step 3: `InMemorySessionStore` 구현**

```python
# shared/session/adapters/memory.py
from datetime import datetime, timezone
from threading import Lock

from shared.session.base import SessionMeta, SessionStore, StoredMessage


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, SessionMeta]] = {}
        self._messages: dict[str, list[StoredMessage]] = {}
        self._lock = Lock()

    def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        with self._lock:
            if thread_id in self._sessions:
                return
            meta = SessionMeta(
                thread_id=thread_id,
                title=title,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._sessions[thread_id] = (user_id, meta)
            self._messages[thread_id] = []

    def list_sessions(self, user_id: str) -> list[SessionMeta]:
        with self._lock:
            result = [
                meta
                for uid, meta in self._sessions.values()
                if uid == user_id
            ]
            return sorted(result, key=lambda m: m.created_at, reverse=True)

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        with self._lock:
            return list(self._messages.get(thread_id, []))

    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[str]
    ) -> None:
        with self._lock:
            if thread_id not in self._messages:
                return
            self._messages[thread_id].append(
                StoredMessage(role=role, content=content, sources=sources)
            )

    def delete_session(self, thread_id: str, user_id: str) -> None:
        with self._lock:
            entry = self._sessions.get(thread_id)
            if entry is None or entry[0] != user_id:
                return
            del self._sessions[thread_id]
            del self._messages[thread_id]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_session_store.py -v
```

Expected: 7개 PASS

- [ ] **Step 5: Commit**

```bash
git add shared/session/adapters/memory.py tests/shared/test_session_store.py
git commit -m "feat(session): InMemorySessionStore 구현 및 단위 테스트"
```

---

## Task 3: Config 확장 + Factory

**Files:**
- Modify: `shared/config.py`
- Create: `shared/session/factory.py`

- [ ] **Step 1: `shared/config.py` 에 필드 추가**

`Config` dataclass에 두 필드를 추가한다 (기존 `reranker_api_key` 바로 아래):

```python
    reranker_api_key: str     # "" → openai_api_key fallback
    session_store_type: str   # "memory" | "postgres"
    postgres_dsn: str         # prod: postgresql://user:pass@host/db
```

`load_config()` 의 `return Config(...)` 블록 끝에 추가:

```python
        session_store_type=os.getenv("SESSION_STORE_TYPE", "memory"),
        postgres_dsn=os.getenv("POSTGRES_DSN", ""),
```

- [ ] **Step 2: `shared/session/factory.py` 작성**

```python
from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore


def create_session_store(config: Config) -> SessionStore:
    if config.session_store_type == "postgres":
        raise NotImplementedError(
            "PostgresSessionStore is not yet implemented. "
            "Set SESSION_STORE_TYPE=memory for development."
        )
    return InMemorySessionStore()
```

- [ ] **Step 3: 기존 config 테스트 통과 확인**

```bash
pytest tests/shared/test_config.py -v
```

Expected: 전부 PASS (기존 테스트 무영향)

- [ ] **Step 4: Commit**

```bash
git add shared/config.py shared/session/factory.py
git commit -m "feat(session): config에 session_store_type 추가, SessionStore factory 구현"
```

---

## Task 4: deps.py 싱글턴 등록 + Sessions API

**Files:**
- Modify: `app/api/deps.py`
- Create: `app/api/sessions.py`
- Modify: `app/api/chat.py`
- Create: `tests/app/api/test_sessions.py`

- [ ] **Step 1: `app/api/deps.py` 에 세션 스토어 추가**

파일 상단 import 블록에 추가:

```python
from shared.session.base import SessionStore
from shared.session.factory import create_session_store
```

`_rate_limiter` 선언 바로 아래에 추가:

```python
_session_store: SessionStore = create_session_store(_config)


def get_session_store() -> SessionStore:
    return _session_store
```

- [ ] **Step 2: `app/api/sessions.py` 작성**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.auth.base import AuthUser
from app.api.deps import get_current_user, get_session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    thread_id: str
    title: str
    created_at: str


class MessageOut(BaseModel):
    role: str
    content: str
    sources: list[str]


@router.get("", response_model=list[SessionOut])
def list_sessions(user: AuthUser = Depends(get_current_user)):
    store = get_session_store()
    return [
        SessionOut(thread_id=s.thread_id, title=s.title, created_at=s.created_at)
        for s in store.list_sessions(user["user_id"])
    ]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    store = get_session_store()
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        MessageOut(role=m.role, content=m.content, sources=m.sources)
        for m in store.get_messages(session_id)
    ]


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
):
    store = get_session_store()
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(session_id, user["user_id"])
```

- [ ] **Step 3: `app/api/chat.py` 수정 — 라우터 등록 + 세션 기록**

파일 상단 import에 추가:

```python
import logging
from app.api.deps import check_rate_limit, get_current_user, get_session_store
from app.api.sessions import router as sessions_router
```

`app.include_router(admin_router)` 바로 아래에 추가:

```python
app.include_router(sessions_router)
```

`chat` 엔드포인트 함수를 다음으로 교체:

```python
@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    is_new_session = req.session_id is None
    thread_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(
        get_graph(),
        req.question,
        config=config,
        user_id=current_user["user_id"],
        allowed_doc_ids=current_user["allowed_doc_ids"],
    )

    store = get_session_store()
    try:
        if is_new_session:
            store.create_session(thread_id, current_user["user_id"], req.question[:20])
        store.add_message(thread_id, "user", req.question, [])
        store.add_message(thread_id, "assistant", result.text, result.sources)
    except Exception:
        logging.exception("session store write failed for thread_id=%s", thread_id)

    return ChatResponse(answer=result.text, sources=result.sources, session_id=thread_id)
```

- [ ] **Step 4: Sessions API 실패 테스트 작성**

```python
# tests/app/api/test_sessions.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from shared.models import Answer
from shared.session.adapters.memory import InMemorySessionStore


def _token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def _patches(store: InMemorySessionStore):
    mock_answer = Answer(text="답변", sources=["doc.md"])
    return (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    )


def test_list_sessions_empty():
    store = InMemorySessionStore()
    with _patches(store)[0], _patches(store)[1], patch("app.api.deps._session_store", store):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json() == []


def test_list_sessions_after_chat():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        client.post("/chat", json={"question": "안녕하세요"}, headers={"Authorization": f"Bearer {token}"})
        sessions = client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).json()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "안녕하세요"[:20]


def test_get_messages_returns_history():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        chat_res = client.post(
            "/chat", json={"question": "질문입니다"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
        msgs = client.get(
            f"/sessions/{chat_res['session_id']}/messages",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"


def test_get_messages_404_for_other_user():
    store = InMemorySessionStore()
    store.create_session("other-session", "bob", "밥의 질문")
    mock_answer = Answer(text="답변", sources=[])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)  # alice
        res = client.get(
            "/sessions/other-session/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404


def test_delete_session():
    store = InMemorySessionStore()
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        chat_res = client.post(
            "/chat", json={"question": "삭제할 질문"}, headers={"Authorization": f"Bearer {token}"}
        ).json()
        session_id = chat_res["session_id"]
        res = client.delete(f"/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 204
        sessions = client.get("/sessions", headers={"Authorization": f"Bearer {token}"}).json()
        assert sessions == []


def test_delete_session_404_for_other_user():
    store = InMemorySessionStore()
    store.create_session("other-session", "bob", "밥의 질문")
    mock_answer = Answer(text="답변", sources=[])
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)  # alice
        res = client.delete(
            "/sessions/other-session", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 404
```

- [ ] **Step 5: 테스트 실행**

```bash
pytest tests/app/api/test_sessions.py -v
```

Expected: 6개 PASS

- [ ] **Step 6: 기존 chat 테스트 회귀 확인**

```bash
pytest tests/app/api/test_chat.py -v
```

Expected: 전부 PASS

- [ ] **Step 7: Commit**

```bash
git add app/api/deps.py app/api/sessions.py app/api/chat.py tests/app/api/test_sessions.py
git commit -m "feat(api): sessions 엔드포인트 추가 및 chat에서 세션 기록"
```

---

## Task 5: 프론트엔드 타입 + API 클라이언트

**Files:**
- Modify: `web/src/types.ts`
- Modify: `web/src/api/client.ts`

- [ ] **Step 1: `web/src/types.ts` 에 타입 추가**

파일 끝에 추가:

```typescript
export interface Session {
  thread_id: string;
  title: string;
  created_at: string; // ISO8601
}

export interface SessionMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
}
```

- [ ] **Step 2: `web/src/api/client.ts` 에 함수 추가**

파일 상단 import에 추가:

```typescript
import type { Session, SessionMessage } from "../types";
```

파일 끝에 추가:

```typescript
export async function getSessions(): Promise<Session[]> {
  return apiFetch<Session[]>("/sessions");
}

export async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  return apiFetch<SessionMessage[]>(`/sessions/${sessionId}/messages`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/sessions/${sessionId}`, { method: "DELETE" });
}
```

- [ ] **Step 3: 기존 client 테스트 통과 확인**

```bash
cd web && npm test -- run src/api/client.test.ts
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/src/types.ts web/src/api/client.ts
git commit -m "feat(web): Session/SessionMessage 타입 추가 및 sessions API 클라이언트 함수"
```

---

## Task 6: SessionSidebar 컴포넌트

**Files:**
- Create: `web/src/chat/SessionSidebar.tsx`
- Create: `web/src/chat/SessionSidebar.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

```typescript
// web/src/chat/SessionSidebar.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SessionSidebar } from "./SessionSidebar";
import type { Session } from "../types";

const TODAY = new Date().toISOString();
const YESTERDAY = new Date(Date.now() - 86400000).toISOString();

const sessions: Session[] = [
  { thread_id: "t1", title: "오늘의 질문", created_at: TODAY },
  { thread_id: "t2", title: "어제의 질문", created_at: YESTERDAY },
];

describe("SessionSidebar", () => {
  it("열린 상태에서 세션 목록을 렌더링한다", () => {
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("오늘의 질문")).toBeInTheDocument();
    expect(screen.getByText("어제의 질문")).toBeInTheDocument();
  });

  it("닫힌 상태에서 너비가 0이다", () => {
    const { container } = render(
      <SessionSidebar
        isOpen={false}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    const aside = container.querySelector("aside")!;
    expect(aside.style.width).toBe("0px");
  });

  it("세션 클릭 시 onSelect가 thread_id로 호출된다", () => {
    const onSelect = vi.fn();
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={onSelect}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("오늘의 질문"));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });

  it("새 대화 버튼 클릭 시 onNew가 호출된다", () => {
    const onNew = vi.fn();
    render(
      <SessionSidebar
        isOpen={true}
        sessions={[]}
        activeSessionId={null}
        onNew={onNew}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("+ 새 대화"));
    expect(onNew).toHaveBeenCalled();
  });

  it("날짜 그룹 레이블이 렌더링된다", () => {
    render(
      <SessionSidebar
        isOpen={true}
        sessions={sessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("오늘")).toBeInTheDocument();
    expect(screen.getByText("어제")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd web && npm test -- run src/chat/SessionSidebar.test.tsx
```

Expected: FAIL (모듈 없음)

- [ ] **Step 3: `SessionSidebar.tsx` 구현**

```tsx
// web/src/chat/SessionSidebar.tsx
import type { Session } from "../types";

interface SessionSidebarProps {
  isOpen: boolean;
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

type DateGroup = "오늘" | "어제" | "이번 주" | "더 이전";

const DATE_GROUP_ORDER: DateGroup[] = ["오늘", "어제", "이번 주", "더 이전"];

function getDateGroup(isoDate: string): DateGroup {
  const diffMs = Date.now() - new Date(isoDate).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "오늘";
  if (diffDays === 1) return "어제";
  if (diffDays <= 7) return "이번 주";
  return "더 이전";
}

function groupSessionsByDate(sessions: Session[]): Record<DateGroup, Session[]> {
  const groups: Record<DateGroup, Session[]> = {
    오늘: [],
    어제: [],
    "이번 주": [],
    "더 이전": [],
  };
  for (const s of sessions) {
    groups[getDateGroup(s.created_at)].push(s);
  }
  return groups;
}

export function SessionSidebar({
  isOpen,
  sessions,
  activeSessionId,
  onNew,
  onSelect,
  onDelete,
}: SessionSidebarProps) {
  const groups = groupSessionsByDate(sessions);

  return (
    <aside
      className="flex flex-col bg-canvas border-r border-hairline flex-shrink-0 overflow-hidden transition-[width] duration-200"
      style={{ width: isOpen ? 200 : 0 }}
    >
      <div className="p-2.5 pb-1.5 flex-shrink-0">
        <button
          onClick={onNew}
          className="w-full bg-primary text-white rounded-pill py-1.5 text-[12px] font-normal"
        >
          + 새 대화
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-1.5 py-1">
        {DATE_GROUP_ORDER.map((group) => {
          const items = groups[group];
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <p className="text-[9px] font-semibold text-ink-mute uppercase tracking-[0.4px] px-1.5 pt-2 pb-1">
                {group}
              </p>
              {items.map((session) => (
                <SessionItem
                  key={session.thread_id}
                  session={session}
                  isActive={session.thread_id === activeSessionId}
                  onSelect={onSelect}
                  onDelete={onDelete}
                />
              ))}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      className={`group flex items-center justify-between rounded-md px-2 py-1.5 mb-0.5 cursor-pointer ${
        isActive ? "bg-primary-muted" : "hover:bg-canvas-soft"
      }`}
      onClick={() => onSelect(session.thread_id)}
    >
      <span
        className={`text-[11px] truncate flex-1 ${
          isActive ? "text-primary font-medium" : "text-ink-mute"
        }`}
      >
        {session.title}
      </span>
      <button
        className="opacity-0 group-hover:opacity-100 text-ink-mute hover:text-ruby ml-1 text-[11px] flex-shrink-0 bg-transparent border-none cursor-pointer"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(session.thread_id);
        }}
        aria-label="세션 삭제"
      >
        🗑
      </button>
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd web && npm test -- run src/chat/SessionSidebar.test.tsx
```

Expected: 5개 PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/chat/SessionSidebar.tsx web/src/chat/SessionSidebar.test.tsx
git commit -m "feat(web): SessionSidebar 컴포넌트 구현 및 테스트"
```

---

## Task 7: ChatPage 통합

**Files:**
- Modify: `web/src/chat/ChatPage.tsx`

- [ ] **Step 1: `ChatPage.tsx` 전체 교체**

```tsx
import { useEffect, useState } from "react";
import { apiFetch, getSessions, getSessionMessages, deleteSession } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../types";
import type { ChatMessage, ChatResponse, Session } from "../types";
import { MessageInput } from "./MessageInput";
import { MessageList } from "./MessageList";
import { SessionSidebar } from "./SessionSidebar";

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem("session_id")
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    if (sessionId) localStorage.setItem("session_id", sessionId);
  }, [sessionId]);

  useEffect(() => {
    getSessions().then(setSessions).catch(() => {});
  }, []);

  const send = async (question: string) => {
    const isNewSession = sessionId === null;
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setPending(true);
    try {
      const res = await apiFetch<ChatResponse>("/chat", {
        method: "POST",
        body: { question, session_id: sessionId },
      });
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
      if (isNewSession) {
        getSessions().then(setSessions).catch(() => {});
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429 && err.retryAfter !== undefined) {
          setError(`요청이 많습니다. ${err.retryAfter}초 후 다시 시도하세요.`);
        } else if (err.status !== 401) {
          setError(err.message || "요청 처리 중 오류가 발생했습니다.");
        }
      } else {
        setError("네트워크 오류가 발생했습니다.");
      }
    } finally {
      setPending(false);
    }
  };

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) return;
    setLoadingHistory(true);
    setError(null);
    try {
      const history = await getSessionMessages(id);
      setMessages(
        history.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
        }))
      );
      setSessionId(id);
      localStorage.setItem("session_id", id);
    } catch {
      setError("세션을 불러오는 중 오류가 발생했습니다.");
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleNewSession = () => {
    setSessionId(null);
    setMessages([]);
    setError(null);
    localStorage.removeItem("session_id");
  };

  const handleDeleteSession = async (id: string) => {
    setSessions((prev) => prev.filter((s) => s.thread_id !== id));
    if (id === sessionId) {
      setSessionId(null);
      setMessages([]);
      localStorage.removeItem("session_id");
    }
    try {
      await deleteSession(id);
    } catch {
      getSessions().then(setSessions).catch(() => {});
    }
  };

  const handleLogout = () => {
    setMessages([]);
    setSessionId(null);
    localStorage.removeItem("session_id");
    logout();
  };

  return (
    <div className="h-screen flex flex-col bg-canvas-soft overflow-hidden">
      <header
        className="flex items-center justify-between border-b border-hairline bg-canvas px-6 py-3 flex-shrink-0"
        style={{ boxShadow: "rgba(0,55,112,0.08) 0 1px 3px" }}
      >
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="flex flex-col gap-[4px] p-1 text-ink-mute hover:text-ink transition-colors"
            aria-label="사이드바 토글"
          >
            <span className="block w-4 h-[1.5px] bg-current rounded" />
            <span className="block w-4 h-[1.5px] bg-current rounded" />
            <span className="block w-4 h-[1.5px] bg-current rounded" />
          </button>
          <h1
            className="text-[20px] font-light text-ink tracking-[-0.2px]"
            style={{ fontFeatureSettings: '"ss01"' }}
          >
            Company RAG
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[13px] text-ink-mute font-normal tracking-[-0.39px]">
            {user?.user_id ?? ""}
          </span>
          <button
            onClick={handleLogout}
            className="text-[14px] font-normal text-primary hover:text-primary-deep transition-colors"
          >
            로그아웃
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <SessionSidebar
          isOpen={sidebarOpen}
          sessions={sessions}
          activeSessionId={sessionId}
          onNew={handleNewSession}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
        />

        <div className="flex flex-col flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto px-4 py-6 max-w-3xl w-full mx-auto">
            {loadingHistory ? (
              <p className="text-[13px] text-ink-mute text-center mt-8">
                대화 기록을 불러오는 중…
              </p>
            ) : (
              <MessageList messages={messages} />
            )}
            {pending && (
              <div className="flex items-center gap-2 mt-4">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-1.5 h-1.5 rounded-pill bg-primary-muted animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </span>
                <span className="text-[13px] text-ink-mute font-normal">
                  답변 생성 중…
                </span>
              </div>
            )}
            {error && (
              <p className="text-[13px] text-ruby font-normal mt-3">{error}</p>
            )}
          </main>

          <div className="max-w-3xl w-full mx-auto px-4 pb-4 flex-shrink-0">
            <MessageInput onSend={send} disabled={pending || loadingHistory} />
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 컴파일 확인**

```bash
cd web && npx tsc --noEmit
```

Expected: 오류 없음

- [ ] **Step 3: 전체 프론트엔드 테스트 실행**

```bash
cd web && npm test -- run
```

Expected: 전체 PASS

- [ ] **Step 4: Commit**

```bash
git add web/src/chat/ChatPage.tsx
git commit -m "feat(web): ChatPage에 SessionSidebar 통합 및 세션 전환/삭제 로직"
```

---

## Task 8: 전체 회귀 확인 + 브랜치 마무리

- [ ] **Step 1: 백엔드 전체 테스트**

```bash
pytest tests/ -v --tb=short
```

Expected: 전부 PASS. 실패 시 원인 수정 후 재실행.

- [ ] **Step 2: eval 회귀 점수 확인**

```bash
python tests/eval/runner.py
```

Expected: 이전 Phase 대비 recall@5 동일 유지 (세션 로직은 RAG 품질에 무관).

- [ ] **Step 3: 개발 서버 실행 후 수동 확인**

```bash
# 터미널 1
uvicorn app.api.chat:app --reload

# 터미널 2
cd web && npm run dev
```

확인 사항:
- 로그인 후 사이드바가 열린 상태로 표시됨
- 질문 전송 후 사이드바에 세션 추가됨 (제목 = 첫 질문 앞 20자)
- 세션 클릭 시 메시지 히스토리 복원됨
- 🗑 클릭 시 세션이 목록에서 사라짐
- ☰ 버튼으로 사이드바 열고 닫기 동작

- [ ] **Step 4: 최종 커밋 + PR 생성**

```bash
git push origin feat/session-sidebar
gh pr create \
  --title "feat: 대화 세션 목록 사이드바" \
  --body "$(cat <<'EOF'
## Summary
- 토글 사이드바(기본 열림)로 세션 목록 표시, 날짜 그룹(오늘/어제/이번 주) 구분
- 세션 클릭 시 메시지 히스토리 복원 (`GET /sessions/{id}/messages`)
- 세션 삭제 (optimistic update + 실패 시 롤백)
- dev: InMemorySessionStore / prod: PostgreSQL 전환 가능 (Factory 패턴)

## DoD
- [x] InMemorySessionStore 단위 테스트 (7개)
- [x] Sessions API 통합 테스트 (6개, 타 유저 격리 포함)
- [x] SessionSidebar 컴포넌트 테스트 (5개)
- [x] eval 회귀 점수 유지

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

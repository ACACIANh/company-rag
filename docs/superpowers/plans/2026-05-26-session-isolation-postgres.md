# 세션 히스토리 격리 및 PostgreSQL 마이그레이션 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자 간 세션 히스토리를 격리하고, InMemorySessionStore를 PostgresSessionStore로 교체해 서버 재시작 후에도 세션·메시지를 영속한다.

**Architecture:** MemorySaver의 `thread_id`를 `{user_id}:{session_id}`로 네임스페이스해 구조적으로 격리하고, `/chat`에서 소유권 검증을 추가한다. `shared/session/adapters/postgres.py`를 신규 작성해 기존 `PostgresCacheBackend`와 동일한 psycopg2 connection pool 패턴을 따른다.

**Tech Stack:** Python 3.11+, psycopg2-binary, FastAPI, pytest

---

## 파일 맵

| 경로 | 역할 |
|---|---|
| `shared/session/adapters/postgres.py` | 신규 — PostgresSessionStore 구현 |
| `shared/session/factory.py` | 수정 — postgres 분기 활성화 |
| `app/api/chat.py` | 수정 — thread_id 네임스페이스 + 소유권 검증 |
| `tests/shared/test_session_store.py` | 수정 — PostgresSessionStore 통합 테스트 추가 |
| `tests/app/api/test_chat.py` | 수정 — thread_id assertion 수정 + 403 테스트 추가 |

---

## Task 1: PostgresSessionStore 구현

**Files:**
- Create: `shared/session/adapters/postgres.py`
- Modify: `tests/shared/test_session_store.py`

- [ ] **Step 1: 통합 테스트 작성 (파일 끝에 추가)**

`tests/shared/test_session_store.py` 파일 끝에 아래 코드를 추가한다.

```python
import os
import pytest
from shared.session.adapters.postgres import PostgresSessionStore


@pytest.fixture
def pg_store():
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set")
    store = PostgresSessionStore(dsn=dsn)
    with store._conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chat_sessions WHERE user_id IN ('alice', 'bob')")
    yield store
    with store._conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM chat_sessions WHERE user_id IN ('alice', 'bob')")


def test_pg_create_and_list(pg_store):
    pg_store.create_session("t1", "alice", "첫 번째 질문")
    sessions = pg_store.list_sessions("alice")
    assert len(sessions) == 1
    assert sessions[0].thread_id == "t1"
    assert sessions[0].title == "첫 번째 질문"


def test_pg_list_only_own_sessions(pg_store):
    pg_store.create_session("t1", "alice", "앨리스 질문")
    pg_store.create_session("t2", "bob", "밥 질문")
    assert len(pg_store.list_sessions("alice")) == 1
    assert len(pg_store.list_sessions("bob")) == 1


def test_pg_add_and_get_messages(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.add_message("t1", "user", "안녕?", [])
    pg_store.add_message("t1", "assistant", "안녕하세요!", ["doc.md"])
    msgs = pg_store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources == ["doc.md"]


def test_pg_delete_session(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.delete_session("t1", "alice")
    assert pg_store.list_sessions("alice") == []
    assert pg_store.get_messages("t1") == []


def test_pg_delete_does_not_affect_other_user(pg_store):
    pg_store.create_session("t1", "alice", "질문")
    pg_store.delete_session("t1", "bob")
    assert len(pg_store.list_sessions("alice")) == 1


def test_pg_create_session_idempotent(pg_store):
    pg_store.create_session("t1", "alice", "첫 질문")
    pg_store.create_session("t1", "alice", "다른 제목")
    assert len(pg_store.list_sessions("alice")) == 1
    assert pg_store.list_sessions("alice")[0].title == "첫 질문"


def test_pg_add_message_to_nonexistent_session_is_noop(pg_store):
    pg_store.add_message("ghost", "user", "내용", [])
    assert pg_store.get_messages("ghost") == []
```

- [ ] **Step 2: `shared/session/adapters/postgres.py` 작성**

```python
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from shared.session.base import SessionMeta, SessionStore, StoredMessage


class PostgresSessionStore(SessionStore):
    def __init__(self, dsn: str, min_conn: int = 1, max_conn: int = 5) -> None:
        self._pool = pool.ThreadedConnectionPool(min_conn, max_conn, dsn)
        self._ensure_tables()

    @contextmanager
    def _conn(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _ensure_tables(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    thread_id   TEXT        PRIMARY KEY,
                    user_id     TEXT        NOT NULL,
                    title       TEXT        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
                ON chat_sessions(user_id)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id          BIGSERIAL   PRIMARY KEY,
                    thread_id   TEXT        NOT NULL
                                    REFERENCES chat_sessions(thread_id) ON DELETE CASCADE,
                    role        TEXT        NOT NULL,
                    content     TEXT        NOT NULL,
                    sources     JSONB       NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
                ON chat_messages(thread_id, created_at)
            """)

    def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_sessions (thread_id, user_id, title)
                VALUES (%s, %s, %s)
                ON CONFLICT (thread_id) DO NOTHING
            """, (thread_id, user_id, title))

    def list_sessions(self, user_id: str) -> list[SessionMeta]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT thread_id, title, created_at
                FROM chat_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            return [
                SessionMeta(
                    thread_id=row["thread_id"],
                    title=row["title"],
                    created_at=row["created_at"].isoformat(),
                )
                for row in cur.fetchall()
            ]

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT role, content, sources
                FROM chat_messages
                WHERE thread_id = %s
                ORDER BY created_at ASC
            """, (thread_id,))
            return [
                StoredMessage(role=row["role"], content=row["content"], sources=row["sources"])
                for row in cur.fetchall()
            ]

    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[str]
    ) -> None:
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages (thread_id, role, content, sources)
                    VALUES (%s, %s, %s, %s)
                """, (thread_id, role, content, psycopg2.extras.Json(sources)))
        except psycopg2.errors.ForeignKeyViolation:
            pass

    def delete_session(self, thread_id: str, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                DELETE FROM chat_sessions
                WHERE thread_id = %s AND user_id = %s
            """, (thread_id, user_id))
```

- [ ] **Step 3: 테스트 실행 확인**

```bash
.venv/bin/pytest tests/shared/test_session_store.py -v
```

Expected:
- 기존 7개 (`not pg_`) → PASSED
- `pg_*` 7개 → SKIPPED (POSTGRES_DSN not set)

- [ ] **Step 4: 커밋**

```bash
git add shared/session/adapters/postgres.py tests/shared/test_session_store.py
git commit -m "feat(session): PostgresSessionStore 구현 및 통합 테스트 추가"
```

> 실제 PostgreSQL 연동 검증 시: `POSTGRES_DSN=postgresql://user:pass@host/db .venv/bin/pytest tests/shared/test_session_store.py -v -k "pg_"`

---

## Task 2: factory.py postgres 분기 활성화

**Files:**
- Modify: `shared/session/factory.py`

- [ ] **Step 1: factory.py 전체 교체**

```python
from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore
from shared.session.adapters.postgres import PostgresSessionStore


def create_session_store(config: Config) -> SessionStore:
    if config.session_store_type == "postgres":
        return PostgresSessionStore(dsn=config.postgres_dsn)
    return InMemorySessionStore()
```

- [ ] **Step 2: import 오류 없음 확인**

```bash
.venv/bin/python -c "from shared.session.factory import create_session_store; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add shared/session/factory.py
git commit -m "feat(session): factory postgres 분기 활성화"
```

---

## Task 3: chat.py — thread_id 네임스페이스 + 소유권 검증 (TDD)

**Files:**
- Modify: `tests/app/api/test_chat.py`
- Modify: `app/api/chat.py`

- [ ] **Step 1: test_chat.py 수정 — 기존 테스트 업데이트 + 신규 테스트 추가**

`tests/app/api/test_chat.py`를 아래 내용으로 전체 교체한다.

```python
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shared.models import Answer
from shared.session.base import SessionMeta


def _get_token(client: TestClient) -> str:
    res = client.post("/auth/token", json={"username": "alice", "password": "alice123"})
    return res.json()["access_token"]


def _owned_store(session_ids: list[str]) -> MagicMock:
    """list_sessions가 주어진 session_id를 소유한 것으로 응답하는 mock store."""
    mock_store = MagicMock()
    mock_store.list_sessions.return_value = [
        MagicMock(thread_id=sid) for sid in session_ids
    ]
    return mock_store


def test_chat_returns_200():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        response = client.post(
            "/chat",
            json={"question": "테스트"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200


def test_chat_response_shape():
    mock_answer = Answer(text="답변 내용", sources=["a.md", "b.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert data["answer"] == "답변 내용"
    assert data["sources"] == ["a.md", "b.md"]


def test_chat_response_includes_session_id():
    mock_answer = Answer(text="답변", sources=["doc.md"])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert len(data["session_id"]) > 0


def test_chat_uses_provided_session_id():
    """클라이언트가 session_id를 넘기면 응답에 그대로 반환되고,
    MemorySaver에는 user_id가 앞에 붙은 thread_id로 전달된다."""
    mock_answer = Answer(text="답변", sources=[])
    mock_store = _owned_store(["my-session-123"])
    with patch("app.api.chat.answer_question", return_value=mock_answer) as mock_aq, \
         patch("app.api.chat.get_graph", return_value=MagicMock()), \
         patch("app.api.chat.get_session_store", return_value=mock_store):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        data = client.post(
            "/chat",
            json={"question": "질문", "session_id": "my-session-123"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    # 클라이언트에게 반환하는 session_id는 원본 UUID
    assert data["session_id"] == "my-session-123"
    # answer_question에 전달되는 thread_id는 {user_id}:{session_id}
    call_config = mock_aq.call_args[1]["config"]
    assert call_config["configurable"]["thread_id"] == "user-alice:my-session-123"


def test_chat_generates_new_session_id_when_not_provided():
    mock_answer = Answer(text="답변", sources=[])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        resp1 = client.post(
            "/chat",
            json={"question": "q1"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp2 = client.post(
            "/chat",
            json={"question": "q2"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert resp1["session_id"] != resp2["session_id"]


def test_chat_returns_403_for_unauthorized_session_id():
    """다른 사용자의 session_id를 넘기면 403을 반환한다."""
    mock_store = _owned_store([])  # alice가 소유한 세션 없음
    with patch("app.api.chat.get_graph", return_value=MagicMock()), \
         patch("app.api.chat.get_session_store", return_value=mock_store):
        from app.api.chat import app
        client = TestClient(app)
        token = _get_token(client)
        response = client.post(
            "/chat",
            json={"question": "질문", "session_id": "other-user-session"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
.venv/bin/pytest tests/app/api/test_chat.py -v
```

Expected:
- `test_chat_uses_provided_session_id` FAIL — thread_id가 아직 네임스페이스되지 않음
- `test_chat_returns_403_for_unauthorized_session_id` FAIL — 소유권 검증 없음

- [ ] **Step 3: `app/api/chat.py` 수정**

파일 전체를 아래로 교체한다.

```python
import logging
import uuid
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.observability.cost_tracker import init_tracker
from shared.observability.sinks.file_sink import FileSink
from shared.reranker.factory import create_reranker
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.deps import check_rate_limit, get_current_user, get_session_store
from app.api.sessions import router as sessions_router

init_tracker([FileSink("logs")])

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=load_config().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(sessions_router)


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    reranker = create_reranker(config)
    return build_graph(retriever=retriever, llm=llm, reranker=reranker)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())
    is_new_session = req.session_id is None
    store = get_session_store()

    if not is_new_session:
        owned = {s.thread_id for s in store.list_sessions(current_user["user_id"])}
        if session_id not in owned:
            raise HTTPException(status_code=403, detail="Session not found")

    thread_id = f"{current_user['user_id']}:{session_id}"
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(
        get_graph(),
        req.question,
        config=config,
        user_id=current_user["user_id"],
        allowed_doc_ids=current_user["allowed_doc_ids"],
    )

    try:
        if is_new_session:
            store.create_session(session_id, current_user["user_id"], req.question[:20])
        store.add_message(session_id, "user", req.question, [])
        store.add_message(session_id, "assistant", result.text, result.sources)
    except Exception:
        logging.exception("session store write failed for session_id=%s", session_id)

    return ChatResponse(answer=result.text, sources=result.sources, session_id=session_id)
```

- [ ] **Step 4: 테스트 실행 → 전체 통과 확인**

```bash
.venv/bin/pytest tests/app/api/test_chat.py -v
```

Expected: 6개 모두 PASSED

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/shared/fga
```

Expected: 기존 테스트 모두 PASSED (FGA 통합 테스트는 POSTGRES_DSN 필요하므로 제외)

- [ ] **Step 6: 커밋**

```bash
git add app/api/chat.py tests/app/api/test_chat.py
git commit -m "feat(chat): thread_id 네임스페이스 및 세션 소유권 검증 추가"
```

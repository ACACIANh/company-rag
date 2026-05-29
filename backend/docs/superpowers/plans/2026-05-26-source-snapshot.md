# Source Snapshot FGA 재검증 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 이력 로드 시 접근 불가 문서가 Source 배지에 노출되는 버그 수정 — 저장 시 문서 메타데이터 스냅샷 보존, 로드 시 FGA 재검증

**Architecture:** `SourceRef` 데이터 클래스를 도입해 소스명 + 메타데이터(sensitivity/team_id/document_id)를 함께 저장한다. `ChromaStore.search()`가 Chunk.metadata를 채우고, `generate_node`가 이를 읽어 `SourceRef` 목록을 생성해 `SessionStore`에 저장한다. `GET /sessions/{id}/messages` 엔드포인트에서 `FGAClient.filter_sources()`로 현재 권한 기준 재검증 후 반환한다. 프론트엔드 변경 없음 (`sources: string[]` 형태 유지).

**Tech Stack:** Python 3.11, FastAPI, psycopg2 JSONB, chromadb, OpenFGA SDK, pytest

---

## 수정 파일 목록

| 파일 | 역할 |
|---|---|
| `shared/models.py` | SourceRef 추가, Answer.sources 타입 변경 |
| `shared/vector_store/chroma_store.py` | Chunk.metadata에 전체 Chroma 메타데이터 채움 |
| `app/graph/nodes/generate.py` | citations를 list[SourceRef]로 생성 |
| `app/graph/state.py` | citations: list[SourceRef]로 타입 변경 |
| `shared/session/base.py` | StoredMessage.sources, SessionStore.add_message 시그니처 변경 |
| `shared/session/adapters/memory.py` | add_message 시그니처 변경 |
| `shared/session/adapters/postgres.py` | JSONB 직렬화/역직렬화 + 구버전 string 호환 |
| `shared/fga/client.py` | filter_sources, _is_accessible 메서드 추가 |
| `app/api/deps.py` | get_fga_client 추가 |
| `app/api/sessions.py` | get_session_messages에 FGA 재검증 적용 |
| `app/api/chat.py` | SourceRef→str 변환 후 ChatResponse 반환, SourceRef를 store에 저장 |
| `tests/shared/test_models.py` | SourceRef 테스트 추가, Answer 테스트 업데이트 |
| `tests/shared/test_vector_store.py` | metadata 전달 테스트 추가 |
| `tests/app/graph/nodes/test_generate.py` | citations SourceRef 검증으로 업데이트 |
| `tests/shared/test_session_store.py` | SourceRef 기반 add/get 테스트, 구버전 호환 테스트 추가 |
| `tests/shared/fga/test_client.py` | filter_sources 테스트 추가 |
| `tests/app/api/test_sessions.py` | FGA 필터링 테스트 추가, 기존 테스트에 mock_fga 패치 추가 |
| `tests/app/api/test_chat.py` | Answer.sources를 SourceRef로 업데이트 |

---

### Task 1: SourceRef 데이터 모델

**Files:**
- Modify: `shared/models.py`
- Modify: `tests/shared/test_models.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_models.py` 끝에 추가:

```python
def test_source_ref_defaults():
    from shared.models import SourceRef
    ref = SourceRef(source="doc.md")
    assert ref.source == "doc.md"
    assert ref.document_id == ""
    assert ref.sensitivity == "public"
    assert ref.team_id == ""


def test_source_ref_with_all_fields():
    from shared.models import SourceRef
    ref = SourceRef(source="salary.md", document_id="doc:123", sensitivity="secret", team_id="team:dev")
    assert ref.document_id == "doc:123"
    assert ref.sensitivity == "secret"
    assert ref.team_id == "team:dev"


def test_answer_sources_are_source_refs():
    from shared.models import Answer, SourceRef
    refs = [SourceRef(source="a.md"), SourceRef(source="b.md")]
    answer = Answer(text="답변", sources=refs)
    assert len(answer.sources) == 2
    assert answer.sources[0].source == "a.md"
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/shared/test_models.py::test_source_ref_defaults -v
```

Expected: `ImportError: cannot import name 'SourceRef'`

- [ ] **Step 3: SourceRef 추가 및 Answer 타입 변경**

`shared/models.py` 전체를 아래로 교체:

```python
from dataclasses import dataclass, field


@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


@dataclass
class SourceRef:
    source: str
    document_id: str = ""
    sensitivity: str = "public"
    team_id: str = ""


@dataclass
class Answer:
    text: str
    sources: list[SourceRef]
    trace: list[dict] | None = None
```

- [ ] **Step 4: 기존 test_answer_defaults 업데이트**

`tests/shared/test_models.py`의 `test_answer_defaults`와 `test_answer_with_trace`를 수정:

```python
def test_answer_defaults():
    from shared.models import Answer, SourceRef
    answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])
    assert answer.text == "답변"
    assert answer.sources[0].source == "doc.md"
    assert answer.trace is None


def test_answer_with_trace():
    from shared.models import Answer, SourceRef
    trace = [{"step": "retrieve", "count": 5}]
    answer = Answer(text="답변", sources=[SourceRef(source="doc.md")], trace=trace)
    assert answer.trace == trace
```

- [ ] **Step 5: 테스트 통과 확인**

```
pytest tests/shared/test_models.py -v
```

Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add shared/models.py tests/shared/test_models.py
git commit -m "feat: SourceRef 데이터 모델 추가 및 Answer.sources 타입 변경"
```

---

### Task 2: ChromaStore Chunk.metadata 채우기

**Files:**
- Modify: `shared/vector_store/chroma_store.py`
- Modify: `tests/shared/test_vector_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_vector_store.py`에 추가 (기존 `test_chroma_store_search` 뒤):

```python
def test_chroma_store_search_populates_metadata(chroma_store):
    from shared.models import Chunk
    chunks = [Chunk(text="내용", source="doc.md", chunk_id="c1")]
    extra = [{"sensitivity": "internal", "team_id": "team:dev", "document_id": "doc:1"}]
    chroma_store.add(chunks, [[0.1, 0.2, 0.3]], extra_metadata=extra)

    results = chroma_store.search(query_embedding=[0.1, 0.2, 0.3], top_k=1)

    assert results[0].chunk.metadata.get("sensitivity") == "internal"
    assert results[0].chunk.metadata.get("team_id") == "team:dev"
    assert results[0].chunk.metadata.get("document_id") == "doc:1"
    assert results[0].chunk.metadata.get("source") == "doc.md"
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/shared/test_vector_store.py::test_chroma_store_search_populates_metadata -v
```

Expected: FAIL — `AssertionError` (metadata가 `{}`)

- [ ] **Step 3: ChromaStore.search() 수정**

`shared/vector_store/chroma_store.py`의 `search()` 메서드에서 Chunk 생성 부분을 수정:

```python
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_filter: dict | None = None,
    ) -> list[SearchResult]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self._collection.count(), 1)),
            where=where_filter,
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            chunk = Chunk(
                text=doc,
                source=meta["source"],
                chunk_id=results["ids"][0][i],
                metadata=meta,
            )
            score = 1.0 - results["distances"][0][i]
            output.append(SearchResult(chunk=chunk, score=score))
        return output
```

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/shared/test_vector_store.py -v
```

Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/vector_store/chroma_store.py tests/shared/test_vector_store.py
git commit -m "feat: ChromaStore.search()에서 Chunk.metadata에 전체 메타데이터 전달"
```

---

### Task 3: generate_node SourceRef 생성 + AgentState 타입 업데이트

**Files:**
- Modify: `app/graph/nodes/generate.py`
- Modify: `app/graph/state.py`
- Modify: `tests/app/graph/nodes/test_generate.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_generate.py`에서 기존 헬퍼와 테스트를 아래로 교체:

```python
from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult, SourceRef
from app.graph.nodes.generate import generate_node


def _make_result(text: str, source: str, sensitivity: str = "public",
                 team_id: str = "", doc_id: str = "") -> SearchResult:
    return SearchResult(
        chunk=Chunk(
            text=text,
            source=source,
            chunk_id="test_id",
            metadata={"sensitivity": sensitivity, "team_id": team_id, "document_id": doc_id},
        ),
        score=0.9,
    )


def test_generate_node_returns_source_refs():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "테스트 답변"

    state = {
        "question": "질문",
        "documents": [_make_result("내용", "doc.md", sensitivity="internal",
                                   team_id="team:dev", doc_id="doc:1")],
    }
    result = generate_node(state, llm=mock_llm)

    assert result["answer"] == "테스트 답변"
    assert len(result["citations"]) == 1
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.source == "doc.md"
    assert ref.sensitivity == "internal"
    assert ref.team_id == "team:dev"
    assert ref.document_id == "doc:1"


def test_generate_node_defaults_to_public_when_no_metadata():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [SearchResult(
            chunk=Chunk(text="내용", source="doc.md", chunk_id="id"), score=0.9
        )],
    }
    result = generate_node(state, llm=mock_llm)
    ref = result["citations"][0]
    assert isinstance(ref, SourceRef)
    assert ref.sensitivity == "public"
    assert ref.team_id == ""
    assert ref.document_id == ""


def test_generate_node_includes_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "질문",
        "documents": [_make_result("중요한 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    called_prompt = mock_llm.complete.call_args[0][0]
    assert "중요한 내용" in called_prompt
    assert "질문" in called_prompt


def test_generate_node_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "재작성된 질문",
        "documents": [_make_result("문서 내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문" in prompt
    assert "원본 질문" not in prompt


def test_generate_node_falls_back_to_question_when_rewritten_empty():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    state = {
        "question": "원본 질문",
        "rewritten_question": "",
        "documents": [_make_result("내용", "doc.md")],
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


def test_generate_node_includes_chat_history_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "답변"

    history = [{"role": "user", "content": "이전 대화 내용"}]
    state = {
        "question": "질문",
        "rewritten_question": "재작성",
        "documents": [_make_result("문서", "doc.md")],
        "chat_history": history,
    }
    generate_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "이전 대화 내용" in prompt
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/app/graph/nodes/test_generate.py::test_generate_node_returns_source_refs -v
```

Expected: FAIL — `AssertionError` (citations가 `["doc.md"]`)

- [ ] **Step 3: generate_node 수정**

`app/graph/nodes/generate.py`의 citations 생성 부분을 변경:

```python
from shared.llm.base import LLMClient
from shared.models import SourceRef
from shared.observability.cost_tracker import get_tracker
from app.graph.prompts import RAG_GENERATE


def generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    context = "\n\n".join(d.chunk.text for d in state["documents"])
    history = state.get("chat_history", [])
    history_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    ) if history else "없음"
    prompt = RAG_GENERATE.format(context=context, question=question, chat_history=history_text)
    text = llm.complete(prompt)

    tracker = get_tracker()
    if tracker:
        input_tokens = len(prompt) // 4
        output_tokens = len(text) // 4
        tracker.track(
            user_id=state.get("user_id", "anonymous"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="unknown",
        )

    citations = [
        SourceRef(
            source=d.chunk.source,
            document_id=d.chunk.metadata.get("document_id", ""),
            sensitivity=d.chunk.metadata.get("sensitivity", "public"),
            team_id=d.chunk.metadata.get("team_id", ""),
        )
        for d in state["documents"]
    ]
    return {"answer": text, "citations": citations}
```

- [ ] **Step 4: AgentState citations 타입 변경**

`app/graph/state.py`를 수정:

```python
from typing import Literal, TypedDict

from shared.models import SearchResult, SourceRef


class AgentState(TypedDict):
    question: str
    rewritten_question: str
    chat_history: list[dict]
    route: Literal["doc_search", "tool_call", "web_search"]
    documents: list[SearchResult]
    relevance_score: float
    retry_count: int
    answer: str
    citations: list[SourceRef]
    hallucination_passed: bool
    confirmed: bool
    tool_input: str
    user_id: str
    allowed_doc_ids: list[str]   # deprecated — FGA 미연동 테스트 stub용
    user_teams: list[str]        # permission_node가 채움
    personal_doc_ids: list[str]  # permission_node가 채움
```

- [ ] **Step 5: 테스트 통과 확인**

```
pytest tests/app/graph/nodes/test_generate.py -v
```

Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/nodes/generate.py app/graph/state.py \
        tests/app/graph/nodes/test_generate.py
git commit -m "feat: generate_node citations를 SourceRef 목록으로 변경"
```

---

### Task 4: SessionStore SourceRef 지원

**Files:**
- Modify: `shared/session/base.py`
- Modify: `shared/session/adapters/memory.py`
- Modify: `shared/session/adapters/postgres.py`
- Modify: `tests/shared/test_session_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_session_store.py`에서 기존 `test_add_and_get_messages`를 수정하고 새 테스트를 추가:

```python
# 파일 맨 위 import에 추가
from shared.models import SourceRef


def test_add_and_get_messages():
    store = _store()
    store.create_session("t1", "alice", "질문")
    ref = SourceRef(source="doc.md", sensitivity="internal", team_id="team:dev", document_id="doc:1")
    store.add_message("t1", "user", "안녕?", [])
    store.add_message("t1", "assistant", "안녕하세요!", [ref])
    msgs = store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources[0].source == "doc.md"
    assert msgs[1].sources[0].sensitivity == "internal"
    assert msgs[1].sources[0].team_id == "team:dev"


def test_source_ref_roundtrip_in_memory():
    store = _store()
    store.create_session("t1", "alice", "질문")
    refs = [
        SourceRef(source="pub.md", sensitivity="public"),
        SourceRef(source="sec.md", sensitivity="secret", document_id="doc:x"),
    ]
    store.add_message("t1", "assistant", "답변", refs)
    msgs = store.get_messages("t1")
    assert msgs[0].sources[0].sensitivity == "public"
    assert msgs[0].sources[1].document_id == "doc:x"
```

PostgreSQL 하위 호환 테스트도 추가:

```python
def test_pg_backward_compat_string_sources(pg_store):
    """구버전 string 형식 sources가 SourceRef(source=..., sensitivity='public')로 역직렬화."""
    pg_store.create_session("t_compat", "alice", "호환 테스트")
    # 직접 old format JSONB 삽입
    with pg_store._conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_messages (thread_id, role, content, sources) "
            "VALUES ('t_compat', 'assistant', '답변', '[\"old.md\", \"legacy.md\"]'::jsonb)"
        )
    msgs = pg_store.get_messages("t_compat")
    assert msgs[0].sources[0].source == "old.md"
    assert msgs[0].sources[0].sensitivity == "public"
    assert msgs[0].sources[1].source == "legacy.md"


def test_pg_source_ref_roundtrip(pg_store):
    pg_store.create_session("t_refs", "alice", "SourceRef 테스트")
    refs = [
        SourceRef(source="int.md", sensitivity="internal", team_id="team:dev", document_id="doc:int"),
        SourceRef(source="pub.md", sensitivity="public"),
    ]
    pg_store.add_message("t_refs", "assistant", "답변", refs)
    msgs = pg_store.get_messages("t_refs")
    assert msgs[0].sources[0].sensitivity == "internal"
    assert msgs[0].sources[0].team_id == "team:dev"
    assert msgs[0].sources[1].sensitivity == "public"
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/shared/test_session_store.py::test_add_and_get_messages -v
```

Expected: FAIL — `TypeError` (sources 시그니처 불일치)

- [ ] **Step 3: shared/session/base.py 수정**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from shared.models import SourceRef


@dataclass
class SessionMeta:
    thread_id: str
    title: str
    created_at: str  # ISO8601


@dataclass
class StoredMessage:
    role: str  # 'user' | 'assistant'
    content: str
    sources: list[SourceRef] = field(default_factory=list)


class SessionStore(ABC):
    @abstractmethod
    def create_session(self, thread_id: str, user_id: str, title: str) -> None: ...

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[SessionMeta]: ...

    @abstractmethod
    def get_messages(self, thread_id: str) -> list[StoredMessage]: ...

    @abstractmethod
    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None: ...

    @abstractmethod
    def delete_session(self, thread_id: str, user_id: str) -> None: ...
```

- [ ] **Step 4: shared/session/adapters/memory.py 수정**

`add_message` 시그니처만 변경 (내부 로직 동일):

```python
from datetime import datetime, timezone
from threading import Lock

from shared.models import SourceRef
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
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
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

- [ ] **Step 5: shared/session/adapters/postgres.py 수정**

```python
import dataclasses
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from shared.models import SourceRef
from shared.session.base import SessionMeta, SessionStore, StoredMessage


def _to_source_ref(item) -> SourceRef:
    if isinstance(item, str):
        return SourceRef(source=item)
    return SourceRef(**item)


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
                StoredMessage(
                    role=row["role"],
                    content=row["content"],
                    sources=[_to_source_ref(item) for item in row["sources"]],
                )
                for row in cur.fetchall()
            ]

    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages (thread_id, role, content, sources)
                    VALUES (%s, %s, %s, %s)
                """, (thread_id, role, content,
                      psycopg2.extras.Json([dataclasses.asdict(s) for s in sources])))
        except psycopg2.errors.ForeignKeyViolation:
            pass

    def delete_session(self, thread_id: str, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                DELETE FROM chat_sessions
                WHERE thread_id = %s AND user_id = %s
            """, (thread_id, user_id))
```

- [ ] **Step 6: 나머지 기존 test_session_store 테스트 업데이트**

기존 `test_add_message_to_nonexistent_session_is_noop`의 `sources=[]` 호출은 `list[SourceRef]`의 빈 목록이므로 변경 불필요.

기존 `test_pg_add_and_get_messages` 업데이트:

```python
def test_pg_add_and_get_messages(pg_store):
    from shared.models import SourceRef
    pg_store.create_session("t1", "alice", "질문")
    ref = SourceRef(source="doc.md")
    pg_store.add_message("t1", "user", "안녕?", [])
    pg_store.add_message("t1", "assistant", "안녕하세요!", [ref])
    msgs = pg_store.get_messages("t1")
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].sources[0].source == "doc.md"
```

- [ ] **Step 7: 테스트 통과 확인**

```
pytest tests/shared/test_session_store.py -v -k "not pg_"
```

Expected: 전체 PASS (pg_ 테스트는 POSTGRES_DSN 없으면 skip)

- [ ] **Step 8: 커밋**

```bash
git add shared/session/base.py \
        shared/session/adapters/memory.py \
        shared/session/adapters/postgres.py \
        tests/shared/test_session_store.py
git commit -m "feat: SessionStore sources를 list[SourceRef]로 변경, PostgreSQL 구버전 호환 처리"
```

---

### Task 5: FGAClient.filter_sources 추가

**Files:**
- Modify: `shared/fga/client.py`
- Modify: `tests/shared/fga/test_client.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/fga/test_client.py` 끝에 추가:

```python
from shared.models import SourceRef


def test_filter_sources_public_always_accessible():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    sources = [SourceRef(source="doc.md", sensitivity="public")]
    result = client.filter_sources(sources, "u1")
    assert [r.source for r in result] == ["doc.md"]


def test_filter_sources_internal_requires_team():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    sources = [
        SourceRef(source="pub.md", sensitivity="public"),
        SourceRef(source="int.md", sensitivity="internal", team_id="team:dev"),
        SourceRef(source="hr.md", sensitivity="internal", team_id="team:hr"),
    ]
    result = client.filter_sources(sources, "u1")
    names = [r.source for r in result]
    assert "pub.md" in names
    assert "int.md" in names
    assert "hr.md" not in names


def test_filter_sources_secret_requires_personal_doc():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    sources = [
        SourceRef(source="salary.md", sensitivity="secret", document_id="doc:salary"),
        SourceRef(source="eval.md", sensitivity="secret", document_id="doc:eval"),
    ]
    result = client.filter_sources(sources, "u1")
    assert len(result) == 1
    assert result[0].source == "salary.md"


def test_filter_sources_unknown_sensitivity_blocked():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=["doc:x"])
    cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    sources = [SourceRef(source="weird.md", sensitivity="unknown")]
    result = client.filter_sources(sources, "u1")
    assert result == []


def test_filter_sources_empty_list():
    client = _client()
    result = client.filter_sources([], "u1")
    assert result == []
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/shared/fga/test_client.py::test_filter_sources_public_always_accessible -v
```

Expected: FAIL — `AttributeError: 'FGAClient' object has no attribute 'filter_sources'`

- [ ] **Step 3: FGAClient에 메서드 추가**

`shared/fga/client.py`의 `build_chroma_filter` 뒤에 추가:

```python
    def filter_sources(self, sources: list, user_id: str) -> list:
        if not sources:
            return []
        perm = self.get_permission(user_id)
        return [s for s in sources if self._is_accessible(s, perm)]

    def _is_accessible(self, src, perm: "UserPermission") -> bool:
        if src.sensitivity == "public":
            return True
        if src.sensitivity == "internal":
            return src.team_id in perm.teams
        if src.sensitivity == "secret":
            return src.document_id in perm.personal_docs
        return False
```

(SourceRef import 없이 duck typing으로 작성해 순환 import 방지)

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/shared/fga/test_client.py -v
```

Expected: 전체 PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/client.py tests/shared/fga/test_client.py
git commit -m "feat: FGAClient.filter_sources로 SourceRef 목록 FGA 재검증"
```

---

### Task 6: sessions.py FGA 재검증 + deps.py get_fga_client

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/sessions.py`
- Modify: `tests/app/api/test_sessions.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/api/test_sessions.py`에 새 테스트 추가 (기존 테스트는 Step 4에서 업데이트):

```python
from shared.models import SourceRef


def test_get_messages_filters_inaccessible_sources():
    """권한 취소된 문서는 세션 이력에서 제거된다."""
    from unittest.mock import MagicMock, patch
    from fastapi.testclient import TestClient
    from shared.session.adapters.memory import InMemorySessionStore

    store = InMemorySessionStore()
    store.create_session("s-filter", "user-alice", "필터 테스트")
    refs = [
        SourceRef(source="public.md", sensitivity="public"),
        SourceRef(source="internal.md", sensitivity="internal", team_id="team:dev"),
    ]
    store.add_message("s-filter", "assistant", "답변", refs)

    mock_fga = MagicMock()
    mock_fga.filter_sources.side_effect = lambda sources, user_id: [
        s for s in sources if s.sensitivity == "public"
    ]
    mock_answer = MagicMock()
    mock_answer.sources = []
    mock_answer.text = "답변"

    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
        patch("app.api.deps._fga_client", mock_fga),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        msgs = client.get(
            "/sessions/s-filter/messages",
            headers={"Authorization": f"Bearer {token}"},
        ).json()

    assert len(msgs) == 1
    assert msgs[0]["sources"] == ["public.md"]
```

- [ ] **Step 2: 실패 확인**

```
pytest tests/app/api/test_sessions.py::test_get_messages_filters_inaccessible_sources -v
```

Expected: FAIL — `AttributeError` 또는 `AssertionError`

- [ ] **Step 3: deps.py에 get_fga_client 추가**

`app/api/deps.py`의 import와 본문에 추가:

```python
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from shared.auth.base import AuthUser
from shared.auth.jwt_handler import decode_token
from shared.config import load_config
from shared.fga.cache import make_cache_backend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig
from shared.rate_limiter.in_memory import InMemoryRateLimiter
from shared.session.base import SessionStore
from shared.session.factory import create_session_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_config = load_config()
_rate_limiter = InMemoryRateLimiter(
    rules={"/chat": _config.rate_limit_per_minute},
    default_limit=_config.rate_limit_per_minute,
)
_session_store: SessionStore = create_session_store(_config)


def _make_fga_client() -> FGAClient:
    fga_config = FGAConfig(
        api_url=_config.fga_api_url,
        store_id=_config.fga_store_id,
        api_key=_config.fga_api_key,
        cache_ttl_seconds=_config.fga_cache_ttl_seconds,
        pg_dsn=_config.postgres_dsn,
    )
    cache = make_cache_backend(_config.fga_cache_backend, _config.postgres_dsn)
    return FGAClient(config=fga_config, cache=cache)


_fga_client: FGAClient = _make_fga_client()


def get_session_store() -> SessionStore:
    return _session_store


def get_fga_client() -> FGAClient:
    return _fga_client


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
    try:
        payload = decode_token(token, secret=_config.jwt_secret)
        return AuthUser(
            user_id=payload["sub"],
            roles=payload["roles"],
            teams=payload.get("teams", []),
            allowed_doc_ids=payload["allowed_doc_ids"],
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if "admin" not in user["roles"]:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def check_rate_limit(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> None:
    if not _rate_limiter.is_allowed(user["user_id"], request.url.path):
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": "60"},
        )
```

- [ ] **Step 4: sessions.py 수정**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.fga.client import FGAClient
from shared.session.base import SessionStore
from app.api.deps import get_current_user, get_fga_client, get_session_store

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
def list_sessions(
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    return [
        SessionOut(thread_id=s.thread_id, title=s.title, created_at=s.created_at)
        for s in store.list_sessions(user["user_id"])
    ]


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    fga_client: FGAClient = Depends(get_fga_client),
):
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    result = []
    for m in store.get_messages(session_id):
        if m.role == "assistant" and m.sources:
            visible = fga_client.filter_sources(m.sources, user["user_id"])
        else:
            visible = m.sources
        result.append(MessageOut(
            role=m.role,
            content=m.content,
            sources=[s.source for s in visible],
        ))
    return result


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
):
    owned = {s.thread_id for s in store.list_sessions(user["user_id"])}
    if session_id not in owned:
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(session_id, user["user_id"])
```

- [ ] **Step 5: 기존 test_sessions.py 테스트에 mock_fga 패치 추가**

기존 테스트들이 `_fga_client`를 사용하므로 모든 `patch` 블록에 추가. `test_list_sessions_empty` 예시:

```python
def test_list_sessions_empty():
    store = InMemorySessionStore()
    mock_fga = MagicMock()
    mock_fga.filter_sources.side_effect = lambda sources, user_id: sources
    with (
        patch("app.api.chat.answer_question", return_value=MagicMock(sources=[], text="")),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
        patch("app.api.deps._fga_client", mock_fga),
    ):
        from app.api.chat import app
        client = TestClient(app)
        token = _token(client)
        res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json() == []
```

나머지 기존 테스트(`test_list_sessions_after_chat`, `test_delete_session`)도 동일 패턴으로 업데이트:

```python
# 1) mock_fga 추가
mock_fga = MagicMock()
mock_fga.filter_sources.side_effect = lambda sources, user_id: sources

# 2) Answer.sources를 list[SourceRef]로 변경
mock_answer = Answer(text="답변", sources=[SourceRef(source="doc.md")])

# 3) patch 블록에 추가
patch("app.api.deps._fga_client", mock_fga),
```

`sources=[]`를 쓰는 테스트(`test_get_messages_404_for_other_user`, `test_delete_session_404_for_other_user`)는 `sources=[]` 그대로 유지 (빈 list는 타입 무관하게 동작).

`test_get_messages_returns_history`의 경우:
```python
def test_get_messages_returns_history():
    store = InMemorySessionStore()
    mock_fga = MagicMock()
    mock_fga.filter_sources.side_effect = lambda sources, user_id: sources
    mock_answer = MagicMock()
    mock_answer.sources = [SourceRef(source="doc.md")]
    mock_answer.text = "답변"
    with (
        patch("app.api.chat.answer_question", return_value=mock_answer),
        patch("app.api.chat.get_graph", return_value=MagicMock()),
        patch("app.api.deps._session_store", store),
        patch("app.api.deps._fga_client", mock_fga),
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
```

- [ ] **Step 6: 테스트 통과 확인**

```
pytest tests/app/api/test_sessions.py -v
```

Expected: 전체 PASS

- [ ] **Step 7: 커밋**

```bash
git add app/api/deps.py app/api/sessions.py tests/app/api/test_sessions.py
git commit -m "feat: sessions API에 FGA 재검증 적용 — 접근 불가 source 필터링"
```

---

### Task 7: chat.py SourceRef→str 변환 + 테스트 업데이트

**Files:**
- Modify: `app/api/chat.py`
- Modify: `tests/app/api/test_chat.py`

- [ ] **Step 1: 실패 테스트 확인**

```
pytest tests/app/api/test_chat.py -v
```

Expected: `Answer(text=..., sources=["doc.md"])` 타입 불일치로 일부 FAIL

- [ ] **Step 2: chat.py 수정**

`app/api/chat.py`의 `/chat` 엔드포인트 반환 부분을 수정:

```python
    store.add_message(session_id, "user", req.question, [])
    store.add_message(session_id, "assistant", result.text, result.sources)
```

(user 메시지는 `[]`, `list[SourceRef]` 빈 목록이므로 변경 불필요)

ChatResponse 반환 부분:

```python
    return ChatResponse(
        answer=result.text,
        sources=[s.source for s in result.sources],
        session_id=session_id,
    )
```

- [ ] **Step 3: test_chat.py 테스트 업데이트**

`Answer` mock을 `SourceRef` 사용으로 변경. 파일 상단에 import 추가:

```python
from shared.models import Answer, SourceRef
```

모든 `Answer(text="답변", sources=["doc.md"])` 형태를 변경:

```python
# 변경 전
Answer(text="답변", sources=["doc.md"])

# 변경 후
Answer(text="답변", sources=[SourceRef(source="doc.md")])
```

`test_chat_response_shape` 업데이트:

```python
def test_chat_response_shape():
    mock_answer = Answer(text="답변 내용", sources=[SourceRef(source="a.md"), SourceRef(source="b.md")])
    with patch("app.api.chat.answer_question", return_value=mock_answer), \
         patch("app.api.chat.get_graph", return_value=MagicMock()), \
         patch("app.api.chat.get_session_store", return_value=MagicMock()):
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
```

`sources=[]`를 사용하는 테스트는 `Answer(text="답변", sources=[])` 그대로 유지.

- [ ] **Step 4: 테스트 통과 확인**

```
pytest tests/app/api/test_chat.py -v
```

Expected: 전체 PASS

- [ ] **Step 5: 전체 테스트 통과 확인**

```
pytest tests/ -v --ignore=tests/load
```

Expected: 전체 PASS (pg_ 테스트는 POSTGRES_DSN 없으면 skip)

- [ ] **Step 6: 회귀 평가**

```
python tests/eval/runner.py
```

점수 하락 시 원인을 명시하고 조치.

- [ ] **Step 7: 최종 커밋**

```bash
git add app/api/chat.py tests/app/api/test_chat.py
git commit -m "feat: chat.py에서 SourceRef→str 변환 후 응답, SourceRef를 SessionStore에 저장"
```

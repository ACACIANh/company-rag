# Chroma → PostgreSQL(pgvector) 마이그레이션 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chroma 벡터 스토어와 psycopg2 드라이버를 완전히 제거하고, asyncpg + pgvector 기반 PostgresVectorStore로 교체하며 모든 DB 드라이버를 asyncpg로 단일화한다.

**Architecture:** asyncpg Pool을 앱 시작 시 생성해 FGA 캐시·세션 스토어·벡터 스토어·FGAClient에 주입한다. 모든 DB 접근 메서드는 `async def`로 전환하고, LangGraph 노드도 async로 바꾼다. `build_chroma_filter()` → `build_pg_filter()` (순수 함수, sync 유지)로 FGA 필터 타입을 `tuple[str, list]`로 변경한다.

**Tech Stack:** asyncpg>=0.29.0, pgvector>=0.3.0, pytest-asyncio>=0.23.0, pgvector/pgvector:pg16 Docker 이미지

---

## 파일 변경 목록

| 경로 | 변경 |
|------|------|
| `requirements.txt` | chromadb 제거, psycopg2-binary 제거, asyncpg/pgvector/pytest-asyncio 추가 |
| `docker-compose.yml` | postgres 이미지 → `pgvector/pgvector:pg16` |
| `shared/vector_store/base.py` | `add()`/`search()` async, filter 타입 변경 |
| `shared/vector_store/postgres_store.py` | 신규: PostgresVectorStore |
| `shared/vector_store/factory.py` | PostgresVectorStore 반환 |
| `shared/vector_store/chroma_store.py` | 삭제 |
| `shared/fga/base.py` | PermissionCacheBackend 메서드 async |
| `shared/fga/cache/memory.py` | InMemoryCacheBackend 메서드 async |
| `shared/fga/cache/postgres.py` | psycopg2 → asyncpg, Pool 주입 |
| `shared/fga/cache/__init__.py` | make_cache_backend 시그니처 변경 |
| `shared/fga/client.py` | build_pg_filter 추가, build_chroma_filter 제거, 전체 async, asyncpg Pool 주입 |
| `shared/session/base.py` | SessionStore 메서드 async |
| `shared/session/adapters/memory.py` | InMemorySessionStore 메서드 async |
| `shared/session/adapters/postgres.py` | psycopg2 → asyncpg, Pool 주입 |
| `shared/session/factory.py` | Pool 파라미터 수용 |
| `shared/retriever/base.py` | `retrieve()` async, filter 타입 변경 |
| `shared/retriever/basic_retriever.py` | async retrieve |
| `shared/indexer/indexer.py` | `index()` async |
| `app/ingestion/indexer.py` | `build_index()` async |
| `app/graph/nodes/retrieve.py` | async, build_pg_filter 사용 |
| `app/graph/nodes/permission.py` | async |
| `app/api/deps.py` | FastAPI lifespan, pool 생성 |
| `shared/config.py` | chroma 필드 제거 |
| `tests/shared/test_vector_store.py` | PostgresVectorStore mock 테스트 |
| `tests/shared/test_config.py` | chroma 어서션 제거 |
| `tests/shared/fga/test_client.py` | build_pg_filter 테스트 |
| `tests/app/graph/nodes/test_retrieve.py` | async, build_pg_filter mock |
| `tests/app/test_rag_with_fga.py` | async, pg filter 적용 |
| `tests/shared/fga/test_postgres_cache.py` | asyncpg mock 기반 재작성 |
| `tests/shared/test_session_store.py` | asyncpg mock 기반 재작성 |

---

## Task 1: 의존성 + 인프라

**Files:**
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`

- [ ] **Step 1: requirements.txt 변경**

```text
# requirements.txt — 변경 후 전체 내용
openai>=1.0.0
anthropic>=0.20.0
sentence-transformers>=2.0.0
python-dotenv>=1.0.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
langchain-community>=0.3.0
langgraph>=0.2.0
pyyaml>=6.0
pytest>=8.0.0
pytest-mock>=3.0.0
pytest-asyncio>=0.23.0
fastapi>=0.110.0
httpx>=0.27.0
tavily-python>=0.3.0
duckduckgo-search>=6.0.0
PyJWT>=2.8.0
locust>=2.29.0
asyncpg>=0.29.0
pgvector>=0.3.0
openfga-sdk>=0.10.0
```

- [ ] **Step 2: docker-compose.yml postgres 이미지 교체**

`docker-compose.yml` 1번째 줄 서비스 블록에서:
```yaml
# 변경 전
image: postgres:16-alpine

# 변경 후
image: pgvector/pgvector:pg16
```

- [ ] **Step 3: 커밋**

```bash
git add requirements.txt docker-compose.yml
git commit -m "chore: chromadb/psycopg2 제거, asyncpg/pgvector 추가, pgvector postgres 이미지"
```

---

## Task 2: 인터페이스 async 전환 — VectorStore + Retriever

**Files:**
- Modify: `shared/vector_store/base.py`
- Modify: `shared/retriever/base.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_vector_store.py` 상단에 추가:
```python
import pytest
import inspect
from shared.vector_store.base import VectorStore

def test_vector_store_add_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.add)

def test_vector_store_search_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.search)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py::test_vector_store_add_is_coroutinefunction -v
```
Expected: FAIL

- [ ] **Step 3: shared/vector_store/base.py 변경**

```python
from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    async def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]: ...

    @abstractmethod
    async def count(self) -> int: ...
```

- [ ] **Step 4: shared/retriever/base.py 변경**

```python
from abc import ABC, abstractmethod
from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]: ...
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/test_vector_store.py::test_vector_store_add_is_coroutinefunction tests/shared/test_vector_store.py::test_vector_store_search_is_coroutinefunction -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add shared/vector_store/base.py shared/retriever/base.py tests/shared/test_vector_store.py
git commit -m "refactor: VectorStore/Retriever 인터페이스 async 전환, pg filter 타입"
```

---

## Task 3: 인터페이스 async 전환 — FGA 캐시 + 세션 스토어

**Files:**
- Modify: `shared/fga/base.py`
- Modify: `shared/fga/cache/memory.py`
- Modify: `shared/session/base.py`
- Modify: `shared/session/adapters/memory.py`

- [ ] **Step 1: shared/fga/base.py 변경**

```python
from abc import ABC, abstractmethod
from shared.fga.models import UserPermission


class PermissionCacheBackend(ABC):
    @abstractmethod
    async def get(self, user_id: str) -> UserPermission | None: ...

    @abstractmethod
    async def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def invalidate(self, user_id: str) -> None: ...
```

- [ ] **Step 2: shared/fga/cache/memory.py 변경**

```python
import time
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class InMemoryCacheBackend(PermissionCacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[UserPermission, float]] = {}

    async def get(self, user_id: str) -> UserPermission | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        perm, expires_at = entry
        if time.time() > expires_at:
            del self._store[user_id]
            return None
        return perm

    async def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        self._store[user_id] = (perm, time.time() + ttl_seconds)

    async def invalidate(self, user_id: str) -> None:
        self._store.pop(user_id, None)
```

- [ ] **Step 3: shared/session/base.py 변경**

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
    async def create_session(self, thread_id: str, user_id: str, title: str) -> None: ...

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[SessionMeta]: ...

    @abstractmethod
    async def get_messages(self, thread_id: str) -> list[StoredMessage]: ...

    @abstractmethod
    async def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None: ...

    @abstractmethod
    async def delete_session(self, thread_id: str, user_id: str) -> None: ...
```

- [ ] **Step 4: shared/session/adapters/memory.py 변경**

```python
from datetime import datetime, timezone

from shared.models import SourceRef
from shared.session.base import SessionMeta, SessionStore, StoredMessage


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str, SessionMeta]] = {}
        self._messages: dict[str, list[StoredMessage]] = {}

    async def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        if thread_id in self._sessions:
            return
        meta = SessionMeta(
            thread_id=thread_id,
            title=title,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sessions[thread_id] = (user_id, meta)
        self._messages[thread_id] = []

    async def list_sessions(self, user_id: str) -> list[SessionMeta]:
        result = [
            meta
            for uid, meta in self._sessions.values()
            if uid == user_id
        ]
        return sorted(result, key=lambda m: m.created_at, reverse=True)

    async def get_messages(self, thread_id: str) -> list[StoredMessage]:
        return list(self._messages.get(thread_id, []))

    async def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        if thread_id not in self._messages:
            return
        self._messages[thread_id].append(
            StoredMessage(role=role, content=content, sources=sources)
        )

    async def delete_session(self, thread_id: str, user_id: str) -> None:
        entry = self._sessions.get(thread_id)
        if entry is None or entry[0] != user_id:
            return
        del self._sessions[thread_id]
        del self._messages[thread_id]
```

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/base.py shared/fga/cache/memory.py shared/session/base.py shared/session/adapters/memory.py
git commit -m "refactor: PermissionCacheBackend/SessionStore 인터페이스 및 InMemory 구현체 async 전환"
```

---

## Task 4: PostgresCacheBackend — asyncpg 마이그레이션

**Files:**
- Modify: `shared/fga/cache/postgres.py`
- Modify: `shared/fga/cache/__init__.py`
- Test: `tests/shared/fga/test_postgres_cache.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/fga/test_postgres_cache.py` 전체 교체:
```python
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.fga.cache.postgres import PostgresCacheBackend
from shared.fga.models import UserPermission


def _make_pool(fetchrow_return=None, execute_called=True):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_get_returns_none_when_no_row():
    pool, conn = _make_pool(fetchrow_return=None)
    backend = PostgresCacheBackend(pool)
    result = await backend.get("u1")
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_permission_when_row_found():
    row = {"teams": json.dumps(["team:dev"]), "personal_docs": json.dumps(["doc:x"])}
    pool, conn = _make_pool(fetchrow_return=row)
    backend = PostgresCacheBackend(pool)
    result = await backend.get("u1")
    assert result is not None
    assert result.teams == ["team:dev"]
    assert result.personal_docs == ["doc:x"]


@pytest.mark.asyncio
async def test_set_calls_execute():
    pool, conn = _make_pool()
    backend = PostgresCacheBackend(pool)
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    await backend.set("u1", perm, ttl_seconds=60)
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_calls_execute():
    pool, conn = _make_pool()
    backend = PostgresCacheBackend(pool)
    await backend.invalidate("u1")
    conn.execute.assert_called_once()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_postgres_cache.py -v
```
Expected: FAIL (import error)

- [ ] **Step 3: shared/fga/cache/postgres.py 전체 교체**

```python
import json
from datetime import datetime, timedelta, timezone

import asyncpg

from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class PostgresCacheBackend(PermissionCacheBackend):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fga_permission_cache (
                    user_id       TEXT PRIMARY KEY,
                    teams         TEXT         NOT NULL DEFAULT '[]',
                    personal_docs TEXT         NOT NULL DEFAULT '[]',
                    expires_at    TIMESTAMPTZ  NOT NULL,
                    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fga_cache_expires
                ON fga_permission_cache(expires_at)
            """)

    async def get(self, user_id: str) -> UserPermission | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT teams, personal_docs FROM fga_permission_cache "
                "WHERE user_id = $1 AND expires_at > now()",
                user_id,
            )
            if row is None:
                return None
            return UserPermission(
                user_id=user_id,
                teams=json.loads(row["teams"]),
                personal_docs=json.loads(row["personal_docs"]),
            )

    async def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO fga_permission_cache (user_id, teams, personal_docs, expires_at, updated_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    teams = EXCLUDED.teams,
                    personal_docs = EXCLUDED.personal_docs,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
            """, user_id, json.dumps(perm.teams), json.dumps(perm.personal_docs), expires_at)

    async def invalidate(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM fga_permission_cache WHERE user_id = $1", user_id
            )
```

- [ ] **Step 4: shared/fga/cache/__init__.py 변경**

```python
import asyncpg

from shared.fga.base import PermissionCacheBackend


def make_cache_backend(
    backend: str, pool: asyncpg.Pool | None = None
) -> PermissionCacheBackend:
    if backend == "postgres" and pool is not None:
        from shared.fga.cache.postgres import PostgresCacheBackend
        return PostgresCacheBackend(pool)
    from shared.fga.cache.memory import InMemoryCacheBackend
    return InMemoryCacheBackend()
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_postgres_cache.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add shared/fga/cache/postgres.py shared/fga/cache/__init__.py tests/shared/fga/test_postgres_cache.py
git commit -m "feat: PostgresCacheBackend psycopg2 → asyncpg 전환"
```

---

## Task 5: PostgresSessionStore — asyncpg 마이그레이션

**Files:**
- Modify: `shared/session/adapters/postgres.py`
- Modify: `shared/session/factory.py`
- Test: `tests/shared/test_session_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_session_store.py` 전체 교체:
```python
import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.session.adapters.postgres import PostgresSessionStore
from shared.models import SourceRef


def _make_pool(fetchrow_return=None, fetch_return=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_create_session_calls_execute():
    pool, conn = _make_pool()
    store = PostgresSessionStore(pool)
    await store.create_session("t1", "u1", "제목")
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_list_sessions_returns_empty():
    pool, conn = _make_pool(fetch_return=[])
    store = PostgresSessionStore(pool)
    result = await store.list_sessions("u1")
    assert result == []


@pytest.mark.asyncio
async def test_add_message_calls_execute():
    pool, conn = _make_pool()
    store = PostgresSessionStore(pool)
    await store.add_message("t1", "user", "안녕", [])
    conn.execute.assert_called_once()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_session_store.py -v
```
Expected: FAIL

- [ ] **Step 3: shared/session/adapters/postgres.py 전체 교체**

```python
import dataclasses
import json

import asyncpg

from shared.models import SourceRef
from shared.session.base import SessionMeta, SessionStore, StoredMessage


def _to_source_ref(item) -> SourceRef:
    if isinstance(item, SourceRef):
        return item
    if isinstance(item, str):
        return SourceRef(source=item)
    return SourceRef(**item)


class PostgresSessionStore(SessionStore):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_tables(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    thread_id   TEXT        PRIMARY KEY,
                    user_id     TEXT        NOT NULL,
                    title       TEXT        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
                ON chat_sessions(user_id)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id          BIGSERIAL   PRIMARY KEY,
                    thread_id   TEXT        NOT NULL
                                    REFERENCES chat_sessions(thread_id) ON DELETE CASCADE,
                    role        TEXT        NOT NULL,
                    content     TEXT        NOT NULL,
                    sources     TEXT        NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
                ON chat_messages(thread_id, created_at)
            """)

    async def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chat_sessions (thread_id, user_id, title)
                VALUES ($1, $2, $3)
                ON CONFLICT (thread_id) DO NOTHING
            """, thread_id, user_id, title)

    async def list_sessions(self, user_id: str) -> list[SessionMeta]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT thread_id, title, created_at
                FROM chat_sessions
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            return [
                SessionMeta(
                    thread_id=row["thread_id"],
                    title=row["title"],
                    created_at=row["created_at"].isoformat(),
                )
                for row in rows
            ]

    async def get_messages(self, thread_id: str) -> list[StoredMessage]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, sources
                FROM chat_messages
                WHERE thread_id = $1
                ORDER BY created_at ASC
            """, thread_id)
            return [
                StoredMessage(
                    role=row["role"],
                    content=row["content"],
                    sources=[_to_source_ref(item) for item in json.loads(row["sources"])],
                )
                for row in rows
            ]

    async def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO chat_messages (thread_id, role, content, sources)
                    VALUES ($1, $2, $3, $4)
                """, thread_id, role, content,
                    json.dumps([dataclasses.asdict(s) for s in sources]))
            except asyncpg.ForeignKeyViolationError:
                pass

    async def delete_session(self, thread_id: str, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM chat_sessions
                WHERE thread_id = $1 AND user_id = $2
            """, thread_id, user_id)
```

- [ ] **Step 4: shared/session/factory.py 변경**

```python
import asyncpg

from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore
from shared.session.adapters.postgres import PostgresSessionStore


def create_session_store(config: Config, pool: asyncpg.Pool | None = None) -> SessionStore:
    if config.session_store_type == "postgres" and pool is not None:
        return PostgresSessionStore(pool=pool)
    return InMemorySessionStore()
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/test_session_store.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add shared/session/adapters/postgres.py shared/session/factory.py tests/shared/test_session_store.py
git commit -m "feat: PostgresSessionStore psycopg2 → asyncpg 전환"
```

---

## Task 6: PostgresVectorStore 구현

**Files:**
- Create: `shared/vector_store/postgres_store.py`
- Modify: `shared/vector_store/factory.py`
- Test: `tests/shared/test_vector_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_vector_store.py` 전체 교체:
```python
import pytest
import inspect
from unittest.mock import AsyncMock, MagicMock
from shared.vector_store.base import VectorStore
from shared.models import Chunk


def test_vector_store_is_abstract():
    with pytest.raises(TypeError):
        VectorStore()


def test_vector_store_add_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.add)


def test_vector_store_search_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.search)


def _make_pool(fetchrow_return=None, fetch_return=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=0)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_postgres_store_add_calls_execute():
    from shared.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool()
    store = PostgresVectorStore(pool)
    chunks = [Chunk(text="안녕", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]
    extra = [{"sensitivity": "public", "team_id": "", "owner_id": "sys", "doc_id": "doc:1"}]
    await store.add(chunks, embeddings, extra_metadata=extra)
    conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_postgres_store_search_returns_empty_on_no_rows():
    from shared.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool(fetch_return=[])
    store = PostgresVectorStore(pool)
    results = await store.search([0.1, 0.2, 0.3], top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_postgres_store_count_returns_int():
    from shared.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool()
    conn.fetchval = AsyncMock(return_value=3)
    store = PostgresVectorStore(pool)
    assert await store.count() == 3
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/test_vector_store.py::test_postgres_store_add_calls_execute -v
```
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: shared/vector_store/postgres_store.py 생성**

```python
import json

import asyncpg
from pgvector.asyncpg import register_vector

from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class PostgresVectorStore(VectorStore):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    chunk_id    TEXT        UNIQUE NOT NULL,
                    content     TEXT        NOT NULL,
                    embedding   vector(1536),
                    metadata    TEXT        NOT NULL DEFAULT '{}',
                    team_id     TEXT        NOT NULL DEFAULT '',
                    sensitivity TEXT        NOT NULL DEFAULT 'public',
                    owner_id    TEXT        NOT NULL DEFAULT '',
                    doc_id      TEXT        NOT NULL DEFAULT '',
                    source      TEXT        NOT NULL DEFAULT '',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_hnsw "
                "ON documents USING hnsw (embedding vector_cosine_ops)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_filter "
                "ON documents (team_id, sensitivity)"
            )

    async def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None:
        rows = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            meta = extra_metadata[i] if extra_metadata and i < len(extra_metadata) else {}
            rows.append((
                chunk.chunk_id,
                chunk.text,
                emb,
                json.dumps({**chunk.metadata, "source": chunk.source, **meta}),
                meta.get("team_id", ""),
                meta.get("sensitivity", "public"),
                meta.get("owner_id", ""),
                meta.get("document_id", meta.get("doc_id", "")),
                chunk.source,
            ))
        async with self._pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO documents
                    (chunk_id, content, embedding, metadata, team_id, sensitivity, owner_id, doc_id, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    team_id = EXCLUDED.team_id,
                    sensitivity = EXCLUDED.sensitivity,
                    owner_id = EXCLUDED.owner_id,
                    doc_id = EXCLUDED.doc_id,
                    source = EXCLUDED.source
            """, rows)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        params = params or []
        emb_param_idx = len(params) + 1
        limit_param_idx = emb_param_idx + 1
        where_sql = f"AND ({where_clause})" if where_clause else ""
        sql = f"""
            SELECT chunk_id, content, source, metadata,
                   1 - (embedding <=> ${emb_param_idx}) AS score
            FROM documents
            WHERE embedding IS NOT NULL {where_sql}
            ORDER BY embedding <=> ${emb_param_idx}
            LIMIT ${limit_param_idx}
        """
        all_params = params + [query_embedding, top_k]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *all_params)
        output = []
        for row in rows:
            meta = json.loads(row["metadata"])
            chunk = Chunk(
                text=row["content"],
                source=row["source"],
                chunk_id=row["chunk_id"],
                metadata=meta,
            )
            output.append(SearchResult(chunk=chunk, score=float(row["score"])))
        return output

    async def count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM documents")
```

- [ ] **Step 4: shared/vector_store/factory.py 변경**

```python
import asyncpg

from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.postgres_store import PostgresVectorStore


def create_vector_store(config: Config, pool: asyncpg.Pool) -> VectorStore:
    return PostgresVectorStore(pool)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/shared/test_vector_store.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add shared/vector_store/postgres_store.py shared/vector_store/factory.py tests/shared/test_vector_store.py
git commit -m "feat: PostgresVectorStore(asyncpg+pgvector) 구현, Chroma factory 교체"
```

---

## Task 7: FGAClient — build_pg_filter + 전체 async 전환

**Files:**
- Modify: `shared/fga/client.py`
- Test: `tests/shared/fga/test_client.py`

- [ ] **Step 1: build_pg_filter 실패 테스트 작성**

`tests/shared/fga/test_client.py` 교체 — build_chroma_filter 테스트를 build_pg_filter로 변환:
```python
import pytest
from unittest.mock import AsyncMock, patch

from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.fga.cache.memory import InMemoryCacheBackend
from shared.models import SourceRef


def _client() -> FGAClient:
    config = FGAConfig(api_url="http://localhost:8080", store_id="test-store")
    return FGAClient(config=config, cache=InMemoryCacheBackend())


def test_build_pg_filter_public_only():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert params == []


def test_build_pg_filter_with_teams():
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev", "team:ops"], personal_docs=[])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "team_id = ANY" in clause
    assert "sensitivity = 'internal'" in clause
    assert ["team:dev", "team:ops"] in params


def test_build_pg_filter_with_personal_docs():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "doc_id = ANY" in clause
    assert ["doc:salary"] in params


def test_build_pg_filter_full():
    client = _client()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=["doc:review"])
    clause, params = client.build_pg_filter(perm)
    assert "sensitivity = 'public'" in clause
    assert "team_id = ANY" in clause
    assert "doc_id = ANY" in clause
    assert ["team:dev"] in params
    assert ["doc:review"] in params


@pytest.mark.asyncio
async def test_get_permission_returns_cached():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    await cache.set("u1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_fetch_from_fga", new=AsyncMock()) as mock_fetch:
        result = await client.get_permission("u1")

    mock_fetch.assert_not_called()
    assert result.teams == ["team:dev"]


@pytest.mark.asyncio
async def test_get_permission_calls_fga_on_cache_miss():
    cache = InMemoryCacheBackend()
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)
    expected = UserPermission(user_id="u2", teams=["team:hr"], personal_docs=["doc:eval"])

    with patch.object(client, "_fetch_from_fga", new=AsyncMock(return_value=expected)):
        result = await client.get_permission("u2")

    assert result.teams == ["team:hr"]
    cached = await cache.get("u2")
    assert cached is not None
    assert cached.teams == ["team:hr"]


@pytest.mark.asyncio
async def test_write_tuples_invalidates_cache():
    cache = InMemoryCacheBackend()
    perm = UserPermission(user_id="owner1", teams=["team:dev"], personal_docs=[])
    await cache.set("owner1", perm, ttl_seconds=60)
    client = FGAClient(config=FGAConfig(api_url="http://localhost", store_id="s"), cache=cache)

    with patch.object(client, "_write_fga_tuples", new=AsyncMock()):
        await client.write_tuples("doc:x", "owner1", "team:dev", "internal")

    assert await cache.get("owner1") is None


def test_filter_sources_public_always_accessible():
    client = _client()
    perm = UserPermission(user_id="u1", teams=[], personal_docs=[])
    src = SourceRef(source="pub.md", sensitivity="public")
    assert client._is_accessible(src, perm) is True


def test_filter_sources_internal_requires_team():
    client = _client()
    perm_member = UserPermission(user_id="u1", teams=["team:dev"], personal_docs=[])
    perm_non_member = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="int.md", sensitivity="internal", team_id="team:dev")
    assert client._is_accessible(src, perm_member) is True
    assert client._is_accessible(src, perm_non_member) is False


def test_filter_sources_secret_requires_personal_doc():
    client = _client()
    perm_allowed = UserPermission(user_id="u1", teams=[], personal_docs=["doc:salary"])
    perm_denied = UserPermission(user_id="u2", teams=[], personal_docs=[])
    src = SourceRef(source="sec.md", sensitivity="secret", document_id="doc:salary")
    assert client._is_accessible(src, perm_allowed) is True
    assert client._is_accessible(src, perm_denied) is False
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/shared/fga/test_client.py::test_build_pg_filter_public_only -v
```
Expected: FAIL

- [ ] **Step 3: shared/fga/client.py 전체 교체**

```python
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


class FGAClient:
    def __init__(
        self,
        config: FGAConfig,
        cache: PermissionCacheBackend,
        pg_pool=None,   # asyncpg.Pool | None
    ) -> None:
        self._config = config
        self._cache = cache
        self._pg_pool = pg_pool

    # ── 순수 함수 ────────────────────────────────────────────
    def build_pg_filter(self, perm: UserPermission) -> tuple[str, list]:
        """반환: (WHERE절 문자열, 파라미터 목록). 파라미터 인덱스는 $1부터 순서대로."""
        clauses: list[str] = []
        params: list = []

        clauses.append("sensitivity = 'public'")

        if perm.teams:
            idx = len(params) + 1
            clauses.append(
                f"(team_id = ANY(${idx}) AND sensitivity = 'internal')"
            )
            params.append(perm.teams)

        if perm.personal_docs:
            idx = len(params) + 1
            clauses.append(
                f"(doc_id = ANY(${idx}) AND sensitivity = 'secret')"
            )
            params.append(perm.personal_docs)

        return " OR ".join(clauses), params

    def _is_accessible(self, src: "SourceRef", perm: UserPermission) -> bool:
        if src.sensitivity == "public":
            return True
        if src.sensitivity == "internal":
            return src.team_id in perm.teams
        if src.sensitivity == "secret":
            return src.document_id in perm.personal_docs
        return False

    # ── 캐시 + FGA 연동 (async) ───────────────────────────────
    async def get_permission(self, user_id: str) -> UserPermission:
        cached = await self._cache.get(user_id)
        if cached is not None:
            return cached
        perm = await self._fetch_from_fga(user_id)
        await self._cache.set(user_id, perm, self._config.cache_ttl_seconds)
        return perm

    async def filter_sources(self, sources: list, user_id: str) -> list:
        if not sources:
            return []
        perm = await self.get_permission(user_id)
        return [s for s in sources if self._is_accessible(s, perm)]

    async def _fetch_from_fga(self, user_id: str) -> UserPermission:
        teams = await self._list_fga_objects(f"user:{user_id}", "member", "team")
        personal_docs = await self._query_personal_docs(user_id)
        return UserPermission(user_id=user_id, teams=teams, personal_docs=personal_docs)

    async def _query_personal_docs(self, user_id: str) -> list[str]:
        if self._pg_pool is None:
            return []
        try:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT doc_id FROM user_doc_grants WHERE user_id = $1", user_id
                )
                return [row["doc_id"] for row in rows]
        except Exception:
            return []

    async def _list_fga_objects(self, user: str, relation: str, type_: str) -> list[str]:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientListObjectsRequest
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        if self._config.api_key:
            from openfga_sdk.credentials import CredentialConfiguration, CredentialMethod
            cfg.credentials = CredentialConfiguration(
                method=CredentialMethod.API_TOKEN,
                configuration=CredentialConfiguration(api_token=self._config.api_key),
            )
        async with OpenFgaClient(cfg) as client:
            resp = await client.list_objects(
                ClientListObjectsRequest(user=user, relation=relation, type=type_)
            )
            return resp.objects or []

    async def _write_fga_tuples(self, tuples: list[dict]) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    writes=[ClientTuple(**t) for t in tuples]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise

    @staticmethod
    def _is_idempotent_fga_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "already existed" in msg or "did not exist" in msg

    async def write_tuples(
        self, doc_id: str, owner_id: str, team_id: str, sensitivity: str
    ) -> None:
        fga_obj = f"document:{doc_id.replace(':', '-')}"
        tuples = [{"user": f"user:{owner_id}", "relation": "owner", "object": fga_obj}]
        if sensitivity == "public":
            tuples.append({"user": "user:*", "relation": "viewer", "object": fga_obj})
        elif sensitivity == "internal":
            tuples.append({"user": f"{team_id}#member", "relation": "viewer", "object": fga_obj})
        elif sensitivity == "secret":
            tuples.append({"user": f"user:{owner_id}", "relation": "viewer", "object": fga_obj})
            await self._insert_personal_doc(owner_id, doc_id)
        await self._write_fga_tuples(tuples)
        await self._cache.invalidate(owner_id)

    async def _insert_personal_doc(self, user_id: str, doc_id: str) -> None:
        if self._pg_pool is None:
            return
        async with self._pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_doc_grants (
                    user_id TEXT NOT NULL,
                    doc_id  TEXT NOT NULL,
                    PRIMARY KEY (user_id, doc_id)
                )
            """)
            await conn.execute(
                "INSERT INTO user_doc_grants (user_id, doc_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                user_id, doc_id,
            )

    async def _delete_personal_doc(self, user_id: str, doc_id: str) -> None:
        if self._pg_pool is None:
            return
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_doc_grants WHERE user_id = $1 AND doc_id = $2",
                user_id, doc_id,
            )

    async def add_team_member(self, user_id: str, team_id: str) -> None:
        await self._write_fga_tuples([
            {"user": f"user:{user_id}", "relation": "member", "object": f"team:{team_id}"}
        ])
        await self._cache.invalidate(user_id)

    async def remove_team_member(self, user_id: str, team_id: str) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(
                        user=f"user:{user_id}", relation="member", object=f"team:{team_id}"
                    )]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._cache.invalidate(user_id)

    async def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        await self._write_fga_tuples([
            {"user": f"user:{user_id}", "relation": "viewer", "object": f"document:{doc_id}"}
        ])
        await self._insert_personal_doc(user_id, doc_id)
        await self._cache.invalidate(user_id)

    async def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(
                        user=f"user:{user_id}", relation="viewer", object=f"document:{doc_id}"
                    )]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._delete_personal_doc(user_id, doc_id)
        await self._cache.invalidate(user_id)

    async def delete_user_tuples(self, user_id: str) -> None:
        docs = await self._list_fga_objects(f"user:{user_id}", "viewer", "document")
        teams = await self._list_fga_objects(f"user:{user_id}", "member", "team")
        tuples_to_delete = (
            [{"user": f"user:{user_id}", "relation": "viewer", "object": d} for d in docs]
            + [{"user": f"user:{user_id}", "relation": "member", "object": t} for t in teams]
        )
        if tuples_to_delete:
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            async with OpenFgaClient(cfg) as client:
                try:
                    await client.write(ClientWriteRequest(
                        deletes=[ClientTuple(**t) for t in tuples_to_delete]
                    ))
                except Exception as e:
                    if not self._is_idempotent_fga_error(e):
                        raise
        await self._cache.invalidate(user_id)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/fga/test_client.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/fga/client.py tests/shared/fga/test_client.py
git commit -m "feat: FGAClient build_pg_filter 추가, 전체 async 전환, asyncpg Pool 주입"
```

---

## Task 8: BasicRetriever + Indexer async 전환

**Files:**
- Modify: `shared/retriever/basic_retriever.py`
- Modify: `shared/indexer/indexer.py`

- [ ] **Step 1: BasicRetriever 수정**

`shared/retriever/basic_retriever.py` 전체 교체:
```python
from shared.embedder.base import Embedder
from shared.models import SearchResult
from shared.retriever.base import Retriever
from shared.vector_store.base import VectorStore


class BasicRetriever(Retriever):
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return await self._store.search(
            embedding, top_k=top_k, where_clause=where_clause, params=params
        )
```

- [ ] **Step 2: Indexer async 전환**

`shared/indexer/indexer.py` 전체 교체:
```python
from shared.chunker.base import Chunker
from shared.embedder.base import Embedder
from shared.fga.sensitivity import detect_sensitivity
from shared.loader.base import DocumentLoader
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        fga_client=None,
        default_team_id: str = "team:general",
        default_owner_id: str = "system",
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._fga_client = fga_client
        self._default_team_id = default_team_id
        self._default_owner_id = default_owner_id

    async def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])

        doc_metadata: dict[str, dict] = {}
        for c in chunks:
            if c.source not in doc_metadata:
                full_text = " ".join(ch.text for ch in chunks if ch.source == c.source)
                sensitivity = detect_sensitivity(full_text)
                doc_metadata[c.source] = {
                    "document_id": f"doc:{c.source}",
                    "team_id": self._default_team_id,
                    "sensitivity": sensitivity,
                }

        extra_metadata = [doc_metadata[c.source] for c in chunks]
        await self._store.add(chunks, embeddings, extra_metadata=extra_metadata)

        if self._fga_client:
            for source, meta in doc_metadata.items():
                await self._fga_client.write_tuples(
                    doc_id=meta["document_id"],
                    owner_id=self._default_owner_id,
                    team_id=meta["team_id"],
                    sensitivity=meta["sensitivity"],
                )
        return len(chunks)
```

- [ ] **Step 3: app/ingestion/indexer.py async 전환**

`app/ingestion/indexer.py` 전체 교체:
```python
import asyncpg
from pgvector.asyncpg import register_vector

from shared.config import load_config
from shared.fga.cache import make_cache_backend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


async def build_index(docs_path: str) -> None:
    config = load_config()
    loader = MarkdownLoader()
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn)
    store = create_vector_store(config, pool)

    fga_client = None
    if config.fga_store_id:
        fga_config = FGAConfig(
            api_url=config.fga_api_url,
            store_id=config.fga_store_id,
            api_key=config.fga_api_key,
            cache_ttl_seconds=config.fga_cache_ttl_seconds,
        )
        fga_client = FGAClient(
            config=fga_config,
            cache=make_cache_backend(config.fga_cache_backend, pool),
            pg_pool=pool,
        )

    await Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        fga_client=fga_client,
    ).index(docs_path)

    await pool.close()
```

- [ ] **Step 4: 커밋**

```bash
git add shared/retriever/basic_retriever.py shared/indexer/indexer.py app/ingestion/indexer.py
git commit -m "refactor: BasicRetriever/Indexer async 전환, build_index asyncpg pool 생성"
```

---

## Task 9: 노드 async 전환 — retrieve_node, permission_node

**Files:**
- Modify: `app/graph/nodes/retrieve.py`
- Modify: `app/graph/nodes/permission.py`
- Test: `tests/app/graph/nodes/test_retrieve.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_retrieve.py` 전체 교체:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from shared.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text="내용", source="doc.md") -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test-1"), score=0.9)


def _mock_fga(teams=None, personal_docs=None):
    from shared.fga.models import UserPermission
    client = MagicMock()
    perm = UserPermission(
        user_id="u1", teams=teams or [], personal_docs=personal_docs or []
    )
    if not teams:
        client.build_pg_filter.return_value = ("sensitivity = 'public'", [])
    else:
        client.build_pg_filter.return_value = (
            "sensitivity = 'public' OR (team_id = ANY($1) AND sensitivity = 'internal')",
            [teams],
        )
    return client


@pytest.mark.asyncio
async def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[_make_result()])
    mock_fga = _mock_fga()

    state = {"question": "테스트", "user_id": "u1", "user_teams": [], "personal_doc_ids": []}
    result = await retrieve_node(state, retriever=mock_retriever, fga_client=mock_fga)

    assert "documents" in result
    assert len(result["documents"]) == 1


@pytest.mark.asyncio
async def test_retrieve_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga()

    await retrieve_node(
        {"question": "원본", "rewritten_question": "재작성", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    call_args = mock_retriever.retrieve.call_args
    assert call_args[0][0] == "재작성"


@pytest.mark.asyncio
async def test_retrieve_node_passes_pg_filter():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga(teams=["team:dev"])
    mock_fga.build_pg_filter.return_value = ("sensitivity = 'public'", [])

    await retrieve_node(
        {"question": "q", "user_id": "u1", "user_teams": ["team:dev"], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    _, kwargs = mock_retriever.retrieve.call_args
    assert "where_clause" in kwargs
    assert "params" in kwargs


@pytest.mark.asyncio
async def test_retrieve_node_falls_back_to_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])
    mock_fga = _mock_fga()

    await retrieve_node(
        {"question": "원본", "rewritten_question": "", "user_id": "u1",
         "user_teams": [], "personal_doc_ids": []},
        retriever=mock_retriever, fga_client=mock_fga,
    )
    assert mock_retriever.retrieve.call_args[0][0] == "원본"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: FAIL

- [ ] **Step 3: app/graph/nodes/retrieve.py 변경**

```python
from shared.fga.client import FGAClient
from shared.fga.models import UserPermission
from shared.models import SearchResult
from shared.reranker.base import Reranker
from shared.reranker.noop_reranker import NoOpReranker
from shared.retriever.base import Retriever


async def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    fga_client: FGAClient,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    query = state.get("rewritten_question") or state["question"]
    perm = UserPermission(
        user_id=state.get("user_id", "anonymous"),
        teams=state.get("user_teams", []),
        personal_docs=state.get("personal_doc_ids", []),
    )
    where_clause, params = fga_client.build_pg_filter(perm)
    results: list[SearchResult] = await retriever.retrieve(
        query, top_k=retrieve_top_k, where_clause=where_clause, params=params
    )
    _reranker = reranker or NoOpReranker()
    reranked = _reranker.rerank(query, results, top_k=top_k)
    return {"documents": reranked}
```

- [ ] **Step 4: app/graph/nodes/permission.py 변경**

```python
from shared.fga.client import FGAClient


async def permission_node(state: dict, *, fga_client: FGAClient) -> dict:
    perm = await fga_client.get_permission(state["user_id"])
    return {
        "user_teams": perm.teams,
        "personal_doc_ids": perm.personal_docs,
    }
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/app/graph/nodes/test_retrieve.py -v
```
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add app/graph/nodes/retrieve.py app/graph/nodes/permission.py tests/app/graph/nodes/test_retrieve.py
git commit -m "refactor: retrieve_node/permission_node async 전환, build_pg_filter 적용"
```

---

## Task 10: Config 정리 + chroma_store.py 삭제

**Files:**
- Modify: `shared/config.py`
- Delete: `shared/vector_store/chroma_store.py`
- Modify: `tests/shared/test_config.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/shared/test_config.py`에서 chroma 어서션 제거:
```python
import pytest
from shared.config import Config, load_config


def test_load_config_defaults(monkeypatch):
    for key in ["LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "EMBEDDING_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    config = load_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert not hasattr(config, "chroma_mode")
    assert not hasattr(config, "chroma_path")
    assert not hasattr(config, "vector_store")


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-haiku-20240307")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    config = load_config()

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-3-haiku-20240307"
    assert config.anthropic_api_key == "sk-ant-test"


def test_cors_origins_defaults_to_localhost_vite(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    config = load_config()
    assert config.cors_origins == ["http://localhost:5173"]


def test_cors_origins_parsed_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    config = load_config()
    assert config.cors_origins == ["https://a.example", "https://b.example"]


def test_config_fga_defaults(monkeypatch):
    for key in ["FGA_API_URL", "FGA_STORE_ID", "FGA_API_KEY",
                "FGA_CACHE_BACKEND", "FGA_CACHE_TTL_SECONDS"]:
        monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.fga_api_url == "http://localhost:8080"
    assert config.fga_store_id == ""
    assert config.fga_api_key == ""
    assert config.fga_cache_backend == "memory"
    assert config.fga_cache_ttl_seconds == 60
```

- [ ] **Step 2: shared/config.py 변경**

`chroma_mode`, `chroma_path`, `vector_store` 필드 및 해당 환경변수 제거:
```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS")
    if not raw:
        return ["http://localhost:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass
class Config:
    llm_provider: str
    llm_model: str
    openai_api_key: str
    anthropic_api_key: str
    embedding_model: str
    jwt_secret: str
    jwt_expire_minutes: int
    rate_limit_per_minute: int
    cors_origins: list[str]
    reranker_type: str
    reranker_base_url: str
    reranker_model: str
    reranker_api_key: str
    session_store_type: str
    postgres_dsn: str
    fga_api_url: str
    fga_store_id: str
    fga_api_key: str
    fga_cache_backend: str
    fga_cache_ttl_seconds: int


def load_config() -> Config:
    return Config(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        ),
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-prod"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
        cors_origins=_parse_cors_origins(),
        reranker_type=os.getenv("RERANKER_TYPE", "none"),
        reranker_base_url=os.getenv("RERANKER_BASE_URL", ""),
        reranker_model=os.getenv("RERANKER_MODEL", "gpt-4o-mini"),
        reranker_api_key=os.getenv("RERANKER_API_KEY", ""),
        session_store_type=os.getenv("SESSION_STORE_TYPE", "memory"),
        postgres_dsn=os.getenv("POSTGRES_DSN", ""),
        fga_api_url=os.getenv("FGA_API_URL", "http://localhost:8080"),
        fga_store_id=os.getenv("FGA_STORE_ID", ""),
        fga_api_key=os.getenv("FGA_API_KEY", ""),
        fga_cache_backend=os.getenv("FGA_CACHE_BACKEND", "memory"),
        fga_cache_ttl_seconds=int(os.getenv("FGA_CACHE_TTL_SECONDS", "60")),
    )
```

- [ ] **Step 3: chroma_store.py 삭제**

```bash
rm shared/vector_store/chroma_store.py
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/shared/test_config.py -v
```
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add shared/config.py tests/shared/test_config.py
git rm shared/vector_store/chroma_store.py
git commit -m "chore: Config에서 Chroma 필드 제거, chroma_store.py 삭제"
```

---

## Task 11: deps.py — FastAPI lifespan + asyncpg Pool

**Files:**
- Modify: `app/api/deps.py`

- [ ] **Step 1: app/api/deps.py 변경**

```python
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pgvector.asyncpg import register_vector

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _init_conn(conn):
        await register_vector(conn)

    pool: asyncpg.Pool | None = None
    if _config.postgres_dsn:
        pool = await asyncpg.create_pool(_config.postgres_dsn, init=_init_conn)
        fga_config = FGAConfig(
            api_url=_config.fga_api_url,
            store_id=_config.fga_store_id,
            api_key=_config.fga_api_key,
            cache_ttl_seconds=_config.fga_cache_ttl_seconds,
        )
        app.state.fga_client = FGAClient(
            config=fga_config,
            cache=make_cache_backend(_config.fga_cache_backend, pool),
            pg_pool=pool,
        )
        app.state.session_store = create_session_store(_config, pool)
        app.state.pool = pool
    else:
        fga_config = FGAConfig(
            api_url=_config.fga_api_url,
            store_id=_config.fga_store_id,
            api_key=_config.fga_api_key,
            cache_ttl_seconds=_config.fga_cache_ttl_seconds,
        )
        app.state.fga_client = FGAClient(
            config=fga_config,
            cache=make_cache_backend("memory"),
        )
        app.state.session_store = create_session_store(_config)
        app.state.pool = None

    yield

    if pool:
        await pool.close()


def get_fga_client(request: Request) -> FGAClient:
    return request.app.state.fga_client


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


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

- [ ] **Step 2: FastAPI 앱에 lifespan 연결**

FastAPI 앱이 생성되는 파일(예: `app/api/__init__.py` 또는 앱 진입점)에서:
```python
from app.api.deps import lifespan
app = FastAPI(lifespan=lifespan)
```

- [ ] **Step 3: 커밋**

```bash
git add app/api/deps.py
git commit -m "feat: deps.py FastAPI lifespan으로 asyncpg Pool 생성 및 의존성 주입"
```

---

## Task 12: pytest-asyncio 설정 + conftest.py

**Files:**
- Create or Modify: `pytest.ini` or `pyproject.toml` or `conftest.py`

- [ ] **Step 1: pytest-asyncio 모드 설정**

프로젝트 루트에 `pytest.ini` 파일 확인 후 없으면 생성:
```bash
ls pytest.ini pyproject.toml setup.cfg 2>/dev/null
```

`pytest.ini`가 없으면 루트에 생성:
```ini
[pytest]
asyncio_mode = auto
```

또는 기존 `pytest.ini`/`pyproject.toml`에 추가:
```ini
# pytest.ini
asyncio_mode = auto
```

- [ ] **Step 2: 커밋**

```bash
git add pytest.ini
git commit -m "chore: pytest-asyncio auto 모드 설정"
```

---

## Task 13: test_rag_with_fga.py — pg filter 기반으로 재작성

**Files:**
- Modify: `tests/app/test_rag_with_fga.py`

- [ ] **Step 1: tests/app/test_rag_with_fga.py 전체 교체**

```python
"""
FGA 권한별 pg filter 검색 통합 테스트.
InMemoryCacheBackend + FGA API mock 사용.
retriever.retrieve는 pg filter 조건을 직접 평가.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.fga.cache.memory import InMemoryCacheBackend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig, UserPermission
from shared.models import Chunk, SearchResult


def _make_fga_client(teams=None, personal_docs=None) -> FGAClient:
    config = FGAConfig(api_url="http://localhost", store_id="test")
    client = FGAClient(config=config, cache=InMemoryCacheBackend())
    import asyncio
    perm = UserPermission(user_id="u1", teams=teams or [], personal_docs=personal_docs or [])
    asyncio.get_event_loop().run_until_complete(
        client._cache.set("u1", perm, ttl_seconds=60)
    )
    return client


def _mock_retriever(chunks: list[dict]) -> MagicMock:
    mock = MagicMock()

    async def fake_retrieve(query, top_k=5, where_clause="", params=None):
        results = []
        for chunk_def in chunks:
            text = chunk_def["text"]
            source = chunk_def["source"]
            sensitivity = chunk_def["sensitivity"]
            meta = {
                "sensitivity": sensitivity,
                "source": source,
                "document_id": chunk_def.get("document_id", f"doc:{source}"),
                "team_id": chunk_def.get("team_id", ""),
            }
            if not where_clause or _matches_pg_filter(meta, where_clause, params or []):
                results.append(SearchResult(
                    chunk=Chunk(text=text, source=source, chunk_id=source), score=0.9
                ))
        return results[:top_k]

    mock.retrieve = AsyncMock(side_effect=fake_retrieve)
    return mock


def _matches_pg_filter(meta: dict, where_clause: str, params: list) -> bool:
    sensitivity = meta.get("sensitivity", "")
    team_id = meta.get("team_id", "")
    document_id = meta.get("document_id", "")

    clauses = [c.strip() for c in where_clause.split(" OR ")]
    param_idx = 0

    def _eval_clause(clause: str) -> bool:
        nonlocal param_idx
        if "sensitivity = 'public'" in clause:
            return sensitivity == "public"
        if "team_id = ANY" in clause and "sensitivity = 'internal'" in clause:
            teams = params[param_idx] if param_idx < len(params) else []
            return team_id in teams and sensitivity == "internal"
        if "doc_id = ANY" in clause and "sensitivity = 'secret'" in clause:
            docs = params[param_idx] if param_idx < len(params) else []
            return document_id in docs and sensitivity == "secret"
        return False

    for i, clause in enumerate(clauses):
        if "ANY" in clause:
            result = _eval_clause(clause)
            param_idx += 1
        else:
            result = _eval_clause(clause)
        if result:
            return True
    return False


@pytest.mark.asyncio
async def test_public_doc_accessible_to_all():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "공개 내용", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "공개 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "public.md"


@pytest.mark.asyncio
async def test_internal_doc_blocked_without_team():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "내부 내용", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "내부 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0


@pytest.mark.asyncio
async def test_internal_doc_accessible_with_correct_team():
    fga = _make_fga_client(teams=["team:dev"], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "팀 내부", "source": "internal.md", "sensitivity": "internal", "team_id": "team:dev"},
        {"text": "공개", "source": "public.md", "sensitivity": "public"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "팀 문서", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    sources = [r.chunk.source for r in result["documents"]]
    assert "internal.md" in sources
    assert "public.md" in sources


@pytest.mark.asyncio
async def test_secret_doc_accessible_only_with_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=["doc:salary.md"])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret",
         "document_id": "doc:salary.md"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.source == "salary.md"


@pytest.mark.asyncio
async def test_secret_doc_blocked_without_personal_doc_id():
    fga = _make_fga_client(teams=[], personal_docs=[])
    retriever = _mock_retriever([
        {"text": "급여 내역", "source": "salary.md", "sensitivity": "secret",
         "document_id": "doc:salary.md"},
    ])

    from app.graph.nodes.permission import permission_node
    from app.graph.nodes.retrieve import retrieve_node

    state = {"user_id": "u1", "question": "급여", "user_teams": [], "personal_doc_ids": []}
    perm_result = await permission_node(state, fga_client=fga)
    state.update(perm_result)
    result = await retrieve_node(state, retriever=retriever, fga_client=fga)

    assert len(result["documents"]) == 0
```

- [ ] **Step 2: 테스트 통과 확인**

```bash
pytest tests/app/test_rag_with_fga.py -v
```
Expected: PASS

- [ ] **Step 3: 커밋**

```bash
git add tests/app/test_rag_with_fga.py
git commit -m "test: test_rag_with_fga async + pg filter 기반으로 재작성"
```

---

## Task 14: 전체 테스트 통과 확인

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest --tb=short -q
```
Expected: 모든 테스트 PASS (기존 skip 제외)

- [ ] **Step 2: 회귀 평가 실행** (runner.py 있는 경우)

```bash
python tests/eval/runner.py
```
하락 시 원인 파악 후 조치.

- [ ] **Step 3: 최종 커밋**

```bash
git add -u
git commit -m "chore: Chroma → PostgreSQL(pgvector) 마이그레이션 완료"
```

---

---

## Task 15: FGAConfig pg_dsn 제거 + admin.py + builder.py 정리

**Files:**
- Modify: `shared/fga/models.py`
- Modify: `app/graph/builder.py`
- Modify: `app/api/admin.py`

- [ ] **Step 1: FGAConfig에서 pg_dsn 제거**

`shared/fga/models.py`:
```python
from dataclasses import dataclass, field


@dataclass
class UserPermission:
    user_id: str
    teams: list[str] = field(default_factory=list)
    personal_docs: list[str] = field(default_factory=list)


@dataclass
class FGAConfig:
    api_url: str
    store_id: str
    api_key: str = ""
    cache_ttl_seconds: int = 60
```

- [ ] **Step 2: builder.py — FGAConfig pg_dsn 인자 제거**

`app/graph/builder.py`의 `_default_fga_client()` 함수에서 `pg_dsn` 제거:
```python
def _default_fga_client() -> FGAClient:
    cfg = load_config()
    fga_config = FGAConfig(
        api_url=cfg.fga_api_url,
        store_id=cfg.fga_store_id,
        api_key=cfg.fga_api_key,
        cache_ttl_seconds=cfg.fga_cache_ttl_seconds,
    )
    return FGAClient(config=fga_config, cache=make_cache_backend("memory"))
```

- [ ] **Step 3: admin.py — pool 기반 store + async build_index**

`app/api/admin.py`의 `index_status`와 `index_rebuild`를 pool 주입 방식으로 변경:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
import asyncio
import json
from datetime import date
from pathlib import Path

import yaml

from shared.auth.base import AuthUser
from shared.config import load_config
from app.api.deps import require_admin
from app.ingestion.indexer import build_index

router = APIRouter(prefix="/admin", tags=["admin"])

_config = load_config()


@router.get("/index/status")
async def index_status(
    request: Request,
    _: AuthUser = Depends(require_admin),
) -> dict:
    store = request.app.state.pool  # pool만 확인 (count는 별도 쿼리)
    if store is None:
        return {"chunk_count": 0}
    from shared.vector_store.postgres_store import PostgresVectorStore
    vs = PostgresVectorStore(request.app.state.pool)
    return {"chunk_count": await vs.count()}


@router.post("/index/rebuild", status_code=202)
def index_rebuild(
    background_tasks: BackgroundTasks,
    _: AuthUser = Depends(require_admin),
) -> dict:
    background_tasks.add_task(asyncio.run, build_index("docs/company"))
    return {"status": "rebuilding"}
```

(나머지 admin 엔드포인트는 변경 없이 유지)

- [ ] **Step 4: 커밋**

```bash
git add shared/fga/models.py app/graph/builder.py app/api/admin.py
git commit -m "chore: FGAConfig pg_dsn 제거, builder/admin pool 기반으로 정리"
```

---

## DoD 체크리스트

- [ ] `chromadb`, `psycopg2-binary` requirements에서 제거됨
- [ ] `asyncpg>=0.29.0`, `pgvector>=0.3.0` 추가됨
- [ ] `chroma_store.py` 삭제됨
- [ ] `PostgresVectorStore` 단위 테스트 통과
- [ ] `build_pg_filter` 단위 테스트 통과
- [ ] FGA 캐시/세션 스토어 asyncpg 기반 단위 테스트 통과
- [ ] retrieve_node/permission_node async 테스트 통과
- [ ] 전체 pytest 통과
- [ ] docker-compose postgres 이미지 `pgvector/pgvector:pg16`으로 변경됨

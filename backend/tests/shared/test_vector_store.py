import pytest
import inspect
from unittest.mock import AsyncMock, MagicMock
from core.vector_store.base import VectorStore
from core.models import Chunk


def test_vector_store_is_abstract():
    with pytest.raises(TypeError):
        VectorStore()


def test_vector_store_add_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.add)


def test_vector_store_search_is_coroutinefunction():
    assert inspect.iscoroutinefunction(VectorStore.search)


def _make_pool(fetch_return=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    conn.fetchval = AsyncMock(return_value=0)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_postgres_store_add_calls_executemany():
    from core.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool()
    store = PostgresVectorStore(pool)
    chunks = [Chunk(text="안녕", source="doc.md", chunk_id="c1")]
    embeddings = [[0.1, 0.2, 0.3]]
    extra = [{"sensitivity": "public", "team_id": "", "owner_id": "sys", "doc_id": "doc:1"}]
    await store.add(chunks, embeddings, extra_metadata=extra)
    conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_postgres_store_search_returns_empty_on_no_rows():
    from core.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool(fetch_return=[])
    store = PostgresVectorStore(pool)
    results = await store.search([0.1, 0.2, 0.3], top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_postgres_store_count_returns_int():
    from core.vector_store.postgres_store import PostgresVectorStore
    pool, conn = _make_pool()
    conn.fetchval = AsyncMock(return_value=3)
    store = PostgresVectorStore(pool)
    assert await store.count() == 3

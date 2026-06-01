import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_ensure_table_creates_document_versions():
    from core.document_version.postgres_store import PostgresDocumentVersionStore
    pool, conn = _make_pool()
    store = PostgresDocumentVersionStore(pool)
    await store.ensure_table()
    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS document_versions" in sql
    assert "PRIMARY KEY (document_id, version)" in sql

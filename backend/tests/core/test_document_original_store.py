import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_pool():
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_ensure_table_creates_document_originals():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    await PostgresDocumentOriginalStore(pool).ensure_table()
    sql = conn.execute.call_args_list[0][0][0]
    assert "CREATE TABLE IF NOT EXISTS document_originals" in sql
    assert "PRIMARY KEY (document_id, version)" in sql


@pytest.mark.asyncio
async def test_save_first_version_inserts_version_1():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value=None)  # 기존 버전 없음
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"data"
    )
    insert_sql = conn.execute.call_args[0][0]
    assert "INSERT INTO document_originals" in insert_sql
    assert conn.execute.call_args[0][2] == 1  # version 인자


@pytest.mark.asyncio
async def test_save_same_hash_skips_insert():
    import hashlib

    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    h = hashlib.sha256(b"data").hexdigest()
    conn.fetchrow = AsyncMock(return_value={"version": 3, "content_hash": h})
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"data"
    )
    conn.execute.assert_not_awaited()  # 동일 hash → insert 없음


@pytest.mark.asyncio
async def test_save_changed_hash_bumps_version():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value={"version": 3, "content_hash": "old"})
    conn.execute = AsyncMock()
    await PostgresDocumentOriginalStore(pool).save(
        "/c/eng/a.pdf", "/c/eng", "a.pdf", "application/pdf", b"newdata"
    )
    assert conn.execute.call_args[0][2] == 4  # version+1


@pytest.mark.asyncio
async def test_get_latest_returns_record():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value={
        "document_id": "/c/eng/a.pdf", "version": 2, "folder_path": "/c/eng",
        "filename": "a.pdf", "mime": "application/pdf",
        "original_file": b"data", "content_hash": "h",
    })
    rec = await PostgresDocumentOriginalStore(pool).get_latest("/c/eng/a.pdf")
    assert rec.folder_path == "/c/eng"
    assert rec.original_file == b"data"
    assert rec.filename == "a.pdf"


@pytest.mark.asyncio
async def test_get_latest_missing_returns_none():
    from core.document_original.postgres_store import PostgresDocumentOriginalStore

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    assert await PostgresDocumentOriginalStore(pool).get_latest("/nope") is None

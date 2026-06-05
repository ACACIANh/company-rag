from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from core.session.adapters.postgres import PostgresSessionStore


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


@pytest.mark.asyncio
async def test_add_message_on_fk_violation_noops_and_logs_warning(caplog):
    """삭제된 세션과의 레이스로 FK 위반이 나면 메시지를 조용히 버리되(noop),
    silent 유실을 운영 로그로 추적할 수 있게 thread_id를 warning으로 남긴다."""
    pool, conn = _make_pool()
    conn.execute = AsyncMock(side_effect=asyncpg.ForeignKeyViolationError("fk violation"))
    store = PostgresSessionStore(pool)

    with caplog.at_level("WARNING"):
        await store.add_message("missing-thread", "user", "안녕", [])  # 예외 전파 안 함

    assert any("missing-thread" in r.message for r in caplog.records)

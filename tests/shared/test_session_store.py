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

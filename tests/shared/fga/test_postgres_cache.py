import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.fga.cache.postgres import PostgresCacheBackend
from shared.fga.models import UserPermission


def _make_pool(fetchrow_return=None):
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

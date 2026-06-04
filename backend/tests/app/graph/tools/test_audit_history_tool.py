import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.tools.audit_history_tool import AuditAgent
from core.sql.risk import RISK_DENY, RISK_SELECT


def _fga(has_access=True):
    fga = AsyncMock()
    fga.check = AsyncMock(return_value=has_access)
    return fga


def _pool(rows=None):
    """asyncpg pool mock — acquire()가 async context manager를 반환."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])

    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool, conn


def _make(has_access=True, rows=None):
    fga = _fga(has_access)
    pool, conn = _pool(rows)
    return AuditAgent(fga_client=fga, app_pool=pool), conn


# ── plan() 테스트 ──────────────────────────────────────────────────────────────

def test_plan_defaults_risk_select():
    h, _ = _make()
    action, risk = h.plan({"__caller_id": "u1"})
    assert risk == RISK_SELECT
    params = json.loads(action)
    assert params["limit"] == 20
    assert params["caller_id"] == "u1"


def test_plan_clamps_limit_to_100():
    h, _ = _make()
    action, risk = h.plan({"__caller_id": "u1", "limit": 999})
    params = json.loads(action)
    assert params["limit"] == 100
    assert risk == RISK_SELECT


def test_plan_invalid_decision_returns_deny():
    h, _ = _make()
    _, risk = h.plan({"__caller_id": "u1", "decision": "MAYBE"})
    assert risk == RISK_DENY


def test_plan_missing_caller_id_stores_empty_string():
    h, _ = _make()
    action, risk = h.plan({"limit": 10})
    params = json.loads(action)
    assert params["caller_id"] == ""
    assert risk == RISK_SELECT


def test_plan_preserves_filters():
    h, _ = _make()
    action, _ = h.plan({
        "__caller_id": "admin",
        "limit": 5,
        "user_id": "jisoo",
        "decision": "DENY",
        "start_date": "2026-01-01",
        "end_date": "2026-06-04",
    })
    params = json.loads(action)
    assert params["user_id"] == "jisoo"
    assert params["decision"] == "DENY"
    assert params["start_date"] == "2026-01-01"
    assert params["end_date"] == "2026-06-04"


# ── execute() 테스트 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_empty_caller_id_denied():
    h, _ = _make(has_access=True)
    result = await h.execute(json.dumps({"caller_id": "", "limit": 20}), RISK_SELECT)
    assert "권한 없음" in result


@pytest.mark.asyncio
async def test_execute_non_admin_denied():
    h, _ = _make(has_access=False)
    result = await h.execute(
        json.dumps({"caller_id": "u1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "권한 없음" in result


@pytest.mark.asyncio
async def test_execute_admin_empty_result():
    h, conn = _make(has_access=True, rows=[])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert result == "(결과 없음)"
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_execute_admin_formats_rows():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "created_at": "2026-06-04 10:00:00+00",
        "user_id": "jisoo",
        "gate_decision": "DENY",
        "generated_sql": "SELECT * FROM employees",
        "reason": "capability 미부여",
    }[k]
    h, _ = _make(has_access=True, rows=[row])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "jisoo" in result
    assert "DENY" in result


@pytest.mark.asyncio
async def test_execute_db_error_returns_error_message():
    fga = _fga(has_access=True)
    pool = MagicMock()

    @asynccontextmanager
    async def _bad_acquire():
        raise Exception("connection failed")
        yield  # noqa: unreachable

    pool.acquire = _bad_acquire
    h = AuditAgent(fga_client=fga, app_pool=pool)
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "오류" in result

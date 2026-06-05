import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.tools.audit_history_tool import (
    AuditAgent,
    _clean_result,
    _merge_system_pairs,
    _sql_preview,
)
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
        "department": "개발",
        "role": "c_level",
        "gate_decision": "DENY",
        "generated_sql": "SELECT * FROM employees",
        "reason": "capability 미부여",
        "result_summary": "",
    }[k]
    h, _ = _make(has_access=True, rows=[row])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "jisoo" in result
    assert "DENY" in result
    assert "|" in result  # 마크다운 표 형식
    assert "개발" in result
    assert "c_level" in result


# ── _sql_preview 테스트 ────────────────────────────────────────────────────────

def test_sql_preview_normal_sql():
    assert _sql_preview("SELECT * FROM employees") == "SELECT * FROM employees"

def test_sql_preview_json_shows_label():
    assert _sql_preview('{"caller_id": "u1", "limit": 10}') == "[감사조회]"

def test_sql_preview_truncates_at_50():
    long_sql = "SELECT col1, col2, col3, col4, col5 FROM very_long_table_name WHERE id = 1"
    assert len(_sql_preview(long_sql)) <= 50


# ── _clean_result 테스트 ───────────────────────────────────────────────────────

def test_clean_result_plain_text_unchanged():
    assert _clean_result("1개 행이 변경되었습니다.") == "1개 행이 변경되었습니다."

def test_clean_result_empty_returns_empty():
    assert _clean_result("") == ""

def test_clean_result_markdown_table_single_col():
    # "| salary | | --- | | 80000000 |" → 줄바꿈이 공백으로 치환된 형태
    raw = "| salary |  | --- |  | 80000000 |"
    result = _clean_result(raw)
    assert "salary" in result
    assert "80000000" in result
    assert "\n" not in result
    assert result.count("|") == 0  # pipe 미포함

def test_clean_result_respects_80_char_limit():
    very_long = "| " + " | ".join([f"col{i}" for i in range(20)]) + " |"
    assert len(_clean_result(very_long)) <= 80


# ── _merge_system_pairs 테스트 ─────────────────────────────────────────────────

def _row(user, sql, decision, reason, result=""):
    return {
        "user_id": user,
        "generated_sql": sql,
        "gate_decision": decision,
        "reason": reason,
        "result_summary": result,
        "created_at": "2026-06-04 10:00:00",
        "department": "개발",
        "role": "",
    }


def test_merge_removes_system_row_paired_with_user_row():
    user_row = _row("u1", "SELECT salary", "JUSTIFY_AND_APPROVE", "재확인", "| salary | | --- | | 80000000 |")
    sys_row  = _row("u1", "SELECT salary", "JUSTIFY_AND_APPROVE",
                    "capability justify_bulk_select@capability:sql 보유 → JUSTIFY_AND_APPROVE")
    merged = _merge_system_pairs([user_row, sys_row])
    assert len(merged) == 1
    assert merged[0]["reason"] == "재확인"


def test_merge_keeps_allow_system_row_unpaired():
    sys_row = _row("u1", "SELECT 1", "ALLOW",
                   "capability allow_select@capability:sql 보유 → ALLOW", "결과")
    merged = _merge_system_pairs([sys_row])
    assert len(merged) == 1


def test_merge_keeps_deny_system_row_unpaired():
    sys_row = _row("u2", "UPDATE x", "DENY",
                   "capability update_delete@capability:sql 미부여 → DENY")
    merged = _merge_system_pairs([sys_row])
    assert len(merged) == 1


def test_merge_does_not_collapse_different_users():
    user_row = _row("u1", "SELECT salary", "JUSTIFY_AND_APPROVE", "재확인")
    sys_row  = _row("u2", "SELECT salary", "JUSTIFY_AND_APPROVE",
                    "capability justify_bulk_select@capability:sql 보유 → JUSTIFY_AND_APPROVE")
    merged = _merge_system_pairs([user_row, sys_row])
    assert len(merged) == 2


# ── execute() 테스트 ───────────────────────────────────────────────────────────

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

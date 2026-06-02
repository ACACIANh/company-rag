from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.nodes.sql_execute import sql_execute_node, _format_rows


def _pool(fetch_return=None, fetch_exc=None):
    conn = AsyncMock()
    if fetch_exc is not None:
        conn.fetch = AsyncMock(side_effect=fetch_exc)
    else:
        conn.fetch = AsyncMock(return_value=fetch_return or [])
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


def _state(**over):
    base = {
        "user_id": "user-x",
        "generated_sql": "SELECT name, salary FROM business.employees",
        "gate_decision": "ALLOW",
        "sql_risk": "select",
        "question": "q",
    }
    base.update(over)
    return base


# ── _format_rows ────────────────────────────────────────────
def test_format_rows_empty():
    assert _format_rows([]) == "(결과 없음)"


def test_format_rows_renders_header_and_values():
    out = _format_rows([{"name": "alice", "salary": 100}])
    assert "name" in out and "salary" in out
    assert "alice" in out and "100" in out


# ── sql_execute_node ────────────────────────────────────────
@pytest.mark.asyncio
async def test_executes_and_puts_result_in_documents():
    pool, conn = _pool(fetch_return=[{"name": "alice", "salary": 100}])
    audit = AsyncMock()
    result = await sql_execute_node(_state(), sql_pool=pool, audit_sink=audit)
    assert len(result["documents"]) == 1
    assert "alice" in result["documents"][0].chunk.text
    conn.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_applies_row_limit():
    rows = [{"i": n} for n in range(200)]
    pool, _ = _pool(fetch_return=rows)
    audit = AsyncMock()
    result = await sql_execute_node(_state(), sql_pool=pool, audit_sink=audit, row_limit=5)
    text = result["documents"][0].chunk.text
    # 헤더 1줄 + 최대 5개 데이터 행
    assert len(text.splitlines()) <= 1 + 5


@pytest.mark.asyncio
async def test_execution_error_is_captured_not_raised():
    pool, _ = _pool(fetch_exc=RuntimeError("permission denied"))
    audit = AsyncMock()
    result = await sql_execute_node(_state(), sql_pool=pool, audit_sink=audit)
    assert "오류" in result["documents"][0].chunk.text


@pytest.mark.asyncio
async def test_records_audit_with_result_summary():
    pool, _ = _pool(fetch_return=[{"name": "alice"}])
    audit = AsyncMock()
    await sql_execute_node(_state(), sql_pool=pool, audit_sink=audit)
    audit.record.assert_awaited_once()
    rec = audit.record.call_args[0][0]
    assert rec.gate_decision == "ALLOW"
    assert rec.result_summary   # 결과 요약이 비어있지 않음

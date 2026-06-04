import pytest
from unittest.mock import AsyncMock, MagicMock

from app.graph.tools.sql_tool import SqlAgent, _format_rows
from core.sql.risk import RISK_SELECT, RISK_UPDATE_DELETE


def _pool(fetch_return=None, execute_return="UPDATE 2"):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [{"salary": 100}])
    conn.execute = AsyncMock(return_value=execute_return)
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=None)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=None)))
    return pool, conn


@pytest.mark.asyncio
async def test_select_uses_ro_pool():
    ro, ro_conn = _pool()
    rw, rw_conn = _pool()
    h = SqlAgent(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)
    await h.execute("SELECT salary FROM business.employees WHERE emp_id='x'", RISK_SELECT)
    ro_conn.fetch.assert_awaited_once()
    rw_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_uses_rw_pool_and_reports_rows():
    ro, ro_conn = _pool()
    rw, rw_conn = _pool(execute_return="UPDATE 3")
    h = SqlAgent(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)
    result = await h.execute("UPDATE business.employees SET salary=1 WHERE emp_id='x'", RISK_UPDATE_DELETE)
    rw_conn.execute.assert_awaited_once()
    ro_conn.fetch.assert_not_awaited()
    assert "3" in result


@pytest.mark.asyncio
async def test_update_without_rw_pool_errors():
    ro, _ = _pool()
    h = SqlAgent(llm=MagicMock(), sql_pool=ro, sql_rw_pool=None)
    result = await h.execute("UPDATE business.employees SET salary=1 WHERE emp_id='x'", RISK_UPDATE_DELETE)
    assert "오류" in result


def test_plan_generates_sql_and_classifies_risk():
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT name FROM business.employees WHERE department = 'engineering'", "no"]
    h = SqlAgent(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"question": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"


def test_plan_bulk_pii_upgrades_risk():
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT salary FROM business.employees", "yes"]
    h = SqlAgent(llm=llm, sql_pool=MagicMock())
    _, risk = h.plan({"question": "전직원 급여"})
    assert risk == "bulk_select"


def test_name_and_tool_def():
    h = SqlAgent(llm=MagicMock(), sql_pool=MagicMock())
    assert h.name == "query_business_data"
    assert h.tool.name == "query_business_data"


def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 NL 질문을 추출한다 (ADR-0032)."""
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT name FROM business.employees", "no"]
    h = SqlAgent(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"__arg1": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"


# ── _format_rows 표 형식 테스트 ──────────────────────────────


def test_format_rows_empty():
    assert _format_rows([]) == "(결과 없음)"


def test_format_rows_markdown_table_structure():
    rows = [{"name": "Alice", "salary": 5000}, {"name": "Bob", "salary": 6000}]
    result = _format_rows(rows)
    lines = result.splitlines()
    # 헤더 | 구분선 | 데이터 2행 = 4줄
    assert len(lines) == 4
    assert lines[0] == "| name | salary |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| Alice | 5000 |"
    assert lines[3] == "| Bob | 6000 |"


def test_format_rows_single_column():
    rows = [{"count": 42}]
    result = _format_rows(rows)
    lines = result.splitlines()
    assert lines[0] == "| count |"
    assert lines[1] == "| --- |"
    assert lines[2] == "| 42 |"

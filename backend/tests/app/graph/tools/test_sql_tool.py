from unittest.mock import MagicMock
import pytest

from app.graph.tools.sql_tool import SqlToolHandler


def test_plan_generates_sql_and_classifies_risk():
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT name FROM business.employees WHERE department = 'engineering'", "no"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"question": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"


def test_plan_bulk_pii_upgrades_risk():
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT salary FROM business.employees", "yes"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    _, risk = h.plan({"question": "전직원 급여"})
    assert risk == "bulk_select"


def test_name_and_tool_def():
    h = SqlToolHandler(llm=MagicMock(), sql_pool=MagicMock())
    assert h.name == "query_business_data"
    assert h.tool.name == "query_business_data"


def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 NL 질문을 추출한다 (ADR-0032)."""
    llm = MagicMock()
    llm.complete.side_effect = ["SELECT name FROM business.employees", "no"]
    h = SqlToolHandler(llm=llm, sql_pool=MagicMock())
    planned, risk = h.plan({"__arg1": "엔지니어링 부서원 이름"})
    assert "business.employees" in planned
    assert risk == "select"

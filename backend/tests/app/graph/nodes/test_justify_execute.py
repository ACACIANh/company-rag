from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import ToolMessage

from app.graph.nodes.justify_execute import justify_execute_node
from app.graph.tools.base import ToolResult


def _registry():
    h = MagicMock()
    h.execute = AsyncMock(return_value=ToolResult(text="급여 결과", summary="급여 결과"))
    reg = MagicMock(); reg.handlers = {"query_business_data": h}
    return reg, h


def _fga(roles=(), depts=()):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=list(roles))
    fga.user_departments = AsyncMock(return_value=list(depts))
    return fga


@pytest.mark.asyncio
async def test_executes_pending_when_justified():
    reg, h = _registry()
    state = {
        "confirmed": True, "justification": "사유",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select"}],
        "user_id": "u1",
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock(), fga_client=_fga())
    tms = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tms[0].tool_call_id == "c1" and "급여 결과" in tms[0].content
    assert out["pending_tool_calls"] == []
    h.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejects_pending_when_not_justified():
    reg, h = _registry()
    state = {
        "confirmed": False, "justification": "",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select"}],
        "user_id": "u1",
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock(), fga_client=_fga())
    tms = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert "취소" in tms[0].content or "거부" in tms[0].content
    assert out["pending_tool_calls"] == []
    h.execute.assert_not_called()


@pytest.mark.asyncio
async def test_executed_sql_stored_normalized():
    """저장되는 executed_sql은 소문자·세미콜론 제거 형태다."""
    reg, h = _registry()
    state = {
        "confirmed": True, "justification": "사유",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "UPDATE business.employees SET salary = 70000000 WHERE emp_id = 5;",
                                "risk": "update_delete", "decision": "JUSTIFY_AND_APPROVE"}],
        "user_id": "u1",
        "executed_sql": [],
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock(), fga_client=_fga())
    assert "update business.employees set salary = 70000000 where emp_id = 5" in out["executed_sql"]


@pytest.mark.asyncio
async def test_audit_record_includes_department_role_and_result():
    """justify_execute_node가 FGA에서 부서·역할을 읽어 감사 로그에 포함한다."""
    reg, _ = _registry()
    audit = AsyncMock()
    state = {
        "confirmed": True, "justification": "분석 필요",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select",
                                "decision": "JUSTIFY_AND_APPROVE"}],
        "user_id": "u1", "question": "급여 조회",
    }
    await justify_execute_node(
        state, registry=reg, audit_sink=audit,
        fga_client=_fga(roles=["c_level"], depts=["개발"]),
    )
    record = audit.record.call_args[0][0]
    assert record.department == "개발"
    assert record.role == "c_level"
    assert record.result_summary == "급여 결과"

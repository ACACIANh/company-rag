from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.graph.nodes.tool_gate import tool_gate_node


def _fga(roles, depts):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=depts)
    return fga


def _handler(planned, risk, result="rows"):
    h = MagicMock()
    h.plan.return_value = (planned, risk)
    h.execute = AsyncMock(return_value=result)
    return h


def _registry(handler):
    reg = MagicMock()
    reg.handlers = {"query_business_data": handler}
    return reg


def _ai(tool_calls):
    return AIMessage(content="", tool_calls=tool_calls)


@pytest.mark.asyncio
async def test_allow_executes_and_appends_tool_message():
    handler = _handler("SELECT 1", "select", result="42")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c1"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),
    )
    msgs = out["agent_messages"]
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].tool_call_id == "c1"
    assert "42" in tool_msgs[0].content
    handler.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_deny_appends_rejection_without_executing():
    handler = _handler("UPDATE business.employees SET salary=0", "update_delete")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c2"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),
    )
    tool_msgs = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].tool_call_id == "c2"
    assert "거부" in tool_msgs[0].content or "권한" in tool_msgs[0].content
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_justify_records_pending_without_executing():
    handler = _handler("SELECT salary FROM business.employees", "bulk_select")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c3"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"]), audit_sink=AsyncMock(),
    )
    assert out["pending_tool_calls"]
    pend = out["pending_tool_calls"][0]
    assert pend["id"] == "c3" and pend["decision"] == "JUSTIFY_AND_APPROVE"
    handler.execute.assert_not_called()

from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import ToolMessage

from app.graph.nodes.justify_execute import justify_execute_node


def _registry():
    h = MagicMock()
    h.execute = AsyncMock(return_value="급여 결과")
    reg = MagicMock(); reg.handlers = {"query_business_data": h}
    return reg, h


@pytest.mark.asyncio
async def test_executes_pending_when_justified():
    reg, h = _registry()
    state = {
        "confirmed": True, "justification": "사유",
        "pending_tool_calls": [{"id": "c1", "name": "query_business_data",
                                "planned_action": "SELECT salary", "risk": "bulk_select"}],
        "user_id": "u1",
    }
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock())
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
    out = await justify_execute_node(state, registry=reg, audit_sink=AsyncMock())
    tms = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert "취소" in tms[0].content or "거부" in tms[0].content
    assert out["pending_tool_calls"] == []
    h.execute.assert_not_called()

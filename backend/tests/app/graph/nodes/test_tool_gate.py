from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.graph.nodes.tool_gate import tool_gate_node


def _fga(roles, depts, capabilities=()):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=depts)
    caps = set(capabilities)

    async def check(user, relation, object_):
        return relation in caps

    fga.check = check
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
    audit = AsyncMock()
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c1"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["영업팀"], capabilities=["allow_select"]), audit_sink=audit,
    )
    msgs = out["agent_messages"]
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].tool_call_id == "c1"
    assert "42" in tool_msgs[0].content
    handler.execute.assert_awaited_once()
    record = audit.record.call_args[0][0]
    assert record.result_summary == "42"


@pytest.mark.asyncio
async def test_deny_appends_rejection_without_executing():
    handler = _handler("UPDATE business.employees SET salary=0", "update_delete")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c2"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["영업팀"]), audit_sink=AsyncMock(),
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
        fga_client=_fga([], ["영업팀"], capabilities=["justify_bulk_select"]), audit_sink=AsyncMock(),
    )
    assert out["pending_tool_calls"]
    pend = out["pending_tool_calls"][0]
    assert pend["id"] == "c3" and pend["decision"] == "JUSTIFY_AND_APPROVE"
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_already_executed_sql_different_format_skipped():
    """대소문자·세미콜론이 다른 동등 SQL은 이미 실행된 것으로 차단된다."""
    handler = _handler(
        "UPDATE business.employees SET salary = 70000000 WHERE emp_id = 5;",
        "update_delete",
    )
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c5"}])],
        # 소문자·세미콜론 없는 형태로 이미 저장된 상태
        "executed_sql": ["update business.employees set salary = 70000000 where emp_id = 5"],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["영업팀"], capabilities=["justify_update_delete"]), audit_sink=AsyncMock(),
    )
    tool_msgs = [m for m in out.get("agent_messages", []) if isinstance(m, ToolMessage)]
    assert tool_msgs and "이미 실행" in tool_msgs[0].content
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_caller_id_injected_into_plan():
    """tool_gate_node가 handler.plan() 호출 시 __caller_id를 args에 주입한다."""
    handler = _handler("SELECT 1", "select", result="ok")
    state = {
        "user_id": "jisoo",
        "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c1"}])],
    }
    await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["영업팀"], capabilities=["allow_select"]), audit_sink=AsyncMock(),
    )
    call_args = handler.plan.call_args[0][0]
    assert call_args["__caller_id"] == "jisoo"

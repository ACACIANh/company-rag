from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.graph.nodes.tool_gate import tool_gate_node


def _fga(roles, depts, capabilities=(), tuples=()):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=depts)
    caps = set(capabilities)
    # (relation, object) 정밀 매칭 튜플 — admin@department:Y, can_access@table:X 등.
    exact = set(tuples)

    async def check(user, relation, object_):
        return relation in caps or (relation, object_) in exact

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
        fga_client=_fga([], ["영업"], capabilities=["allow_select"]), audit_sink=audit,
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
        fga_client=_fga([], ["영업"]), audit_sink=AsyncMock(),
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
        # 테이블 게이트(ADR-0047) 통과를 위해 viewer도 부여.
        fga_client=_fga([], ["영업"], capabilities=["justify_bulk_select", "viewer"]),
        audit_sink=AsyncMock(),
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
        fga_client=_fga([], ["영업"], capabilities=["justify_update_delete"]), audit_sink=AsyncMock(),
    )
    tool_msgs = [m for m in out.get("agent_messages", []) if isinstance(m, ToolMessage)]
    assert tool_msgs and "이미 실행" in tool_msgs[0].content
    handler.execute.assert_not_called()


def _perm_registry(handler):
    reg = MagicMock()
    reg.handlers = {"manage_permission": handler}
    return reg


@pytest.mark.asyncio
async def test_table_gate_denies_select_without_can_access():
    """테이블 접근권(can_access) 없으면 SELECT가 허용 위험도여도 최종 DENY (ADR-0047)."""
    handler = _handler("SELECT name FROM business.employees", "select")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "t1"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        # allow_select은 있지만 table:employees can_access 없음.
        fga_client=_fga([], ["영업"], capabilities=["allow_select"]), audit_sink=AsyncMock(),
    )
    tool_msgs = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and ("거부" in tool_msgs[0].content or "권한" in tool_msgs[0].content)
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_table_gate_allows_select_with_viewer():
    """viewer 보유 시 테이블 게이트 통과 → 실행 (ADR-0047)."""
    handler = _handler("SELECT name FROM business.employees", "select", result="rows")
    state = {
        "user_id": "u1", "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "t2"}])],
    }
    out = await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["인사"], capabilities=["allow_select"],
                        tuples={("viewer", "table:employees")}),
        audit_sink=AsyncMock(),
    )
    tool_msgs = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and "rows" in tool_msgs[0].content
    handler.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_dept_admin_membership_delegation_upgrades_to_justify():
    """전역 관리자 아니어도 자기 부서 admin이면 멤버십 grant가 JUSTIFY로 승격 (ADR-0046)."""
    handler = _handler("grant user:user-x member department:개발", "grant")
    state = {
        "user_id": "팀장", "question": "q",
        "agent_messages": [_ai([{"name": "manage_permission", "args": {"instruction": "x"}, "id": "d1"}])],
    }
    out = await tool_gate_node(
        state, registry=_perm_registry(handler),
        # justify_grant(전역) 없음. 대신 admin@department:개발 보유.
        fga_client=_fga([], [], tuples={("admin", "department:개발")}),
        audit_sink=AsyncMock(),
    )
    assert out["pending_tool_calls"]
    assert out["pending_tool_calls"][0]["decision"] == "JUSTIFY_AND_APPROVE"
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_dept_admin_delegation_denied_for_other_dept():
    """다른 부서 admin은 그 부서가 아닌 멤버십을 위임할 수 없다 → DENY (ADR-0046)."""
    handler = _handler("grant user:user-x member department:인사", "grant")
    state = {
        "user_id": "팀장", "question": "q",
        "agent_messages": [_ai([{"name": "manage_permission", "args": {"instruction": "x"}, "id": "d2"}])],
    }
    out = await tool_gate_node(
        state, registry=_perm_registry(handler),
        # 개발 admin이지만 대상은 인사.
        fga_client=_fga([], [], tuples={("admin", "department:개발")}),
        audit_sink=AsyncMock(),
    )
    assert not out["pending_tool_calls"]
    tool_msgs = [m for m in out["agent_messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and ("거부" in tool_msgs[0].content or "권한" in tool_msgs[0].content)
    handler.execute.assert_not_called()


@pytest.mark.asyncio
async def test_dept_admin_cannot_delegate_dept_viewer():
    """부서 admin은 멤버십만 위임 — dept_viewer(폴더권) 위임은 승격되지 않는다 (ADR-0046 경계)."""
    handler = _handler("grant department:개발#member dept_viewer folder:/secret", "grant")
    state = {
        "user_id": "팀장", "question": "q",
        "agent_messages": [_ai([{"name": "manage_permission", "args": {"instruction": "x"}, "id": "d3"}])],
    }
    out = await tool_gate_node(
        state, registry=_perm_registry(handler),
        fga_client=_fga([], [], tuples={("admin", "department:개발")}),
        audit_sink=AsyncMock(),
    )
    assert not out["pending_tool_calls"]
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
        fga_client=_fga([], ["영업"], capabilities=["allow_select"]), audit_sink=AsyncMock(),
    )
    call_args = handler.plan.call_args[0][0]
    assert call_args["__caller_id"] == "jisoo"

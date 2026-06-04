"""도구-실행-전 게이트 인터셉터 (ADR-0023).

에이전트가 부른 각 도구 호출을 plan으로 구체화(SQL의 경우 생성된 SQL+위험도)한 뒤,
신원×위험도 게이트(core.sql.gate)로 ALLOW/JUSTIFY/DENY를 판정한다. ALLOW는 즉시
실행해 ToolMessage를 만들고, DENY는 실행 없이 거부 ToolMessage를, JUSTIFY는
pending_tool_calls에 적재만 한다(HITL은 confirm/justify_execute에서). 모든 결정은
감사 로그(ADR-0018)에 남긴다.
"""
from langchain_core.messages import AIMessage, ToolMessage

from core.fga.client import FGAClient
from core.observability.audit.base import AuditRecord, AuditSink
from core.sql.gate import (
    gate_decision,
    DECISION_ALLOW, DECISION_DENY, DECISION_JUSTIFY_AND_APPROVE,
)

_DENY_TEXT = "거부됨: 현재 권한으로 실행할 수 없는 요청입니다."
_ALREADY_EXECUTED_TEXT = "이미 실행 완료된 SQL입니다. 동일한 작업을 중복 실행하지 않습니다."


def _last_tool_calls(messages: list) -> tuple[AIMessage | None, list]:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return m, m.tool_calls
    return None, []


async def tool_gate_node(state: dict, *, registry, fga_client: FGAClient, audit_sink: AuditSink) -> dict:
    user_id = state["user_id"]
    roles = await fga_client.user_roles(user_id)
    departments = await fga_client.user_departments(user_id)

    _, tool_calls = _last_tool_calls(state.get("agent_messages") or [])
    executed_sql: set[str] = set(state.get("executed_sql") or [])
    new_messages: list = []
    pending: list = []

    for tc in tool_calls:
        handler = registry.handlers.get(tc["name"])
        if handler is None:
            new_messages.append(ToolMessage(content="알 수 없는 도구", tool_call_id=tc["id"]))
            continue
        planned_action, risk = handler.plan(tc["args"])

        if planned_action in executed_sql:
            new_messages.append(ToolMessage(content=_ALREADY_EXECUTED_TEXT, tool_call_id=tc["id"]))
            continue

        decision, reason = await gate_decision(fga_client.check, user_id, risk)

        await audit_sink.record(AuditRecord(
            user_id=user_id,
            department=",".join(departments),
            role=",".join(roles),
            question=state.get("question", ""),
            generated_sql=planned_action,
            sql_risk=risk,
            gate_decision=decision,
            reason=reason,
            result_summary="",
            thread_id=state.get("thread_id", ""),
        ))

        if decision == DECISION_ALLOW:
            result = await handler.execute(planned_action, risk)
            new_messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        elif decision == DECISION_DENY:
            new_messages.append(ToolMessage(content=_DENY_TEXT, tool_call_id=tc["id"]))
        else:  # JUSTIFY_AND_APPROVE
            pending.append({
                "id": tc["id"], "name": tc["name"], "args": tc["args"],
                "planned_action": planned_action, "risk": risk, "decision": decision,
            })

    out: dict = {}
    if new_messages:
        out["agent_messages"] = new_messages
    out["pending_tool_calls"] = pending
    return out

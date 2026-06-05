"""JUSTIFY 사유 입력 후 실행/거부 노드 (ADR-0023/0027).

confirm에서 사유를 받았으면 pending 도구호출을 실행해 ToolMessage를, 빈 사유면 취소
ToolMessage를 만든다. 실행 후 pending을 비우고 에이전트로 복귀한다. 사유는 감사 로그에 남긴다.
"""
from langchain_core.messages import ToolMessage

from app.graph.tools._utils import normalize_sql
from core.fga.client import FGAClient
from core.observability.audit.base import AuditRecord, AuditSink

_CANCEL_TEXT = "취소됨: 사유가 입력되지 않아 실행하지 않았습니다."


async def justify_execute_node(state: dict, *, registry, audit_sink: AuditSink, fga_client: FGAClient) -> dict:
    user_id = state.get("user_id", "")
    try:
        roles = await fga_client.user_roles(user_id) if user_id else []
        departments = await fga_client.user_departments(user_id) if user_id else []
    except Exception:
        roles, departments = [], []

    pending = state.get("pending_tool_calls") or []
    justified = bool(state.get("confirmed")) and bool((state.get("justification") or "").strip())
    messages: list = []

    for p in pending:
        handler = registry.handlers.get(p["name"])
        if justified and handler is not None:
            result = await handler.execute(p["planned_action"], p["risk"])
            messages.append(ToolMessage(content=result.text, tool_call_id=p["id"]))
            reason = state.get("justification", "")
            result_summary = result.summary
        else:
            messages.append(ToolMessage(content=_CANCEL_TEXT, tool_call_id=p["id"]))
            reason = "취소(사유 미기재)"
            result_summary = ""
        await audit_sink.record(AuditRecord(
            user_id=user_id,
            department=",".join(departments),
            role=",".join(roles),
            question=state.get("question", ""),
            generated_sql=p["planned_action"],
            sql_risk=p["risk"],
            gate_decision=p.get("decision", "JUSTIFY_AND_APPROVE"),
            reason=reason,
            result_summary=result_summary,
            thread_id=state.get("thread_id", ""),
        ))

    executed_sql = list(state.get("executed_sql") or [])
    executed_sql.extend(normalize_sql(p["planned_action"]) for p in pending if justified)
    return {"agent_messages": messages, "pending_tool_calls": [], "executed_sql": executed_sql}

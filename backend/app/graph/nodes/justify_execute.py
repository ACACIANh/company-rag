"""JUSTIFY 사유 입력 후 실행/거부 노드 (ADR-0023/0027).

confirm에서 사유를 받았으면 pending 도구호출을 실행해 ToolMessage를, 빈 사유면 취소
ToolMessage를 만든다. 실행 후 pending을 비우고 에이전트로 복귀한다. 사유는 감사 로그에 남긴다.
"""
from langchain_core.messages import ToolMessage

from core.observability.audit.base import AuditRecord, AuditSink

_CANCEL_TEXT = "취소됨: 사유가 입력되지 않아 실행하지 않았습니다."


async def _execute(handler, planned_action: str) -> str:
    if hasattr(handler, "aexecute"):
        return await handler.aexecute(planned_action)
    return handler.execute(planned_action)


async def justify_execute_node(state: dict, *, registry, audit_sink: AuditSink) -> dict:
    pending = state.get("pending_tool_calls") or []
    justified = bool(state.get("confirmed")) and bool((state.get("justification") or "").strip())
    messages: list = []

    for p in pending:
        handler = registry.handlers.get(p["name"])
        if justified and handler is not None:
            result = await _execute(handler, p["planned_action"])
            messages.append(ToolMessage(content=result, tool_call_id=p["id"]))
            reason = state.get("justification", "")
        else:
            messages.append(ToolMessage(content=_CANCEL_TEXT, tool_call_id=p["id"]))
            reason = "취소(사유 미기재)"
        await audit_sink.record(AuditRecord(
            user_id=state.get("user_id", ""), department="", role="",
            question=state.get("question", ""), generated_sql=p["planned_action"],
            sql_risk=p["risk"], gate_decision=p.get("decision", "JUSTIFY_AND_APPROVE"),
            reason=reason, result_summary="", thread_id=state.get("thread_id", ""),
        ))

    return {"agent_messages": messages, "pending_tool_calls": []}

"""사유 기재 자가승인 노드 (ADR-0027, 0023 재배치).

pending_tool_calls의 계획된 동작(SQL 등)을 interrupt 페이로드에 노출하고 사유를
받는다. resume 값은 사유 문자열, 빈 사유는 통과 안 함(미기재 = 실행 안 함).
"""
from langgraph.types import interrupt


def confirm_node(state: dict) -> dict:
    pending = state.get("pending_tool_calls") or []
    actions = [
        {"tool": p["name"], "args": p.get("args", {}), "planned_action": p["planned_action"], "risk": p["risk"]}
        for p in pending
    ]
    response = interrupt({
        "message": "다음 작업은 사유 기재 후 본인 책임으로 실행됩니다. 실행 사유를 입력하세요.",
        "actions": actions,
    })
    justification = response.strip() if isinstance(response, str) else ""
    return {"confirmed": bool(justification), "justification": justification}

"""사유 기재 자가승인 노드 (ADR-0027).

DBA 부재 전제 — 외부 결재자를 기다리는 게 아니라, 질문자 본인이 실행 사유를
기재하고 자기책임으로 통과(JUSTIFY_AND_APPROVE)한다. resume 값은 승인 여부
(boolean)가 아니라 사유 문자열이며, 빈 사유·취소는 통과시키지 않는다(미기재 =
실행 안 함). 기재된 사유는 감사 로그(ADR-0018)에 남도록 state로 흘려보낸다.
"""
from langgraph.types import interrupt


def confirm_node(state: dict) -> dict:
    action = state.get("tool_input") or state["rewritten_question"]
    response = interrupt({
        "message": f"이 작업은 사유 기재 후 본인 책임으로 실행됩니다. 실행 사유를 입력하세요.\n요청: {action}",
        "tool_input": action,
    })
    justification = response.strip() if isinstance(response, str) else ""
    return {"confirmed": bool(justification), "justification": justification}

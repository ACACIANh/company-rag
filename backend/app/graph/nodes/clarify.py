"""사용자 선택 기반 라우팅 노드 (ADR-0042).

모호한 질문에 대해 사용자에게 처리 방식을 선택하도록 interrupt.
반환된 선택지를 내부 route로 맵핑.
"""
from langgraph.types import interrupt

_CLARIFY_OPTIONS = {
    "사내 문서 검색 (RAG)": "doc_search",
    "업무 DB·권한 처리 (에이전트)": "agent",
}


def clarify_node(state: dict) -> dict:
    """
    사용자가 질문 처리 방식을 선택하도록 interrupt.

    Args:
        state: question 필드 포함.

    Returns:
        route (doc_search | agent), tool_input 필드 포함 dict.
    """
    question = state["question"]
    label = interrupt({
        "message": f'"{question}" — 어떤 방식으로 처리할까요?',
        "options": list(_CLARIFY_OPTIONS.keys()),
    })
    route = _CLARIFY_OPTIONS.get(label, "doc_search")
    # agent 경로로 분기 시 tool_input 채움 — router_node와 동일 계약 (ADR-0031)
    return {
        "route": route,
        "tool_input": question if route == "agent" else "",
    }

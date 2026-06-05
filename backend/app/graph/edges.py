"""Conditional routing logic for RAG workflow graph."""

_RELEVANCE_THRESHOLD = 0.5
_MAX_GRADE_RETRIES = 2
_MAX_TOTAL_RETRIES = 3


def route_after_grade(state: dict) -> str:
    """Route after grading document relevance.

    Args:
        state: Graph state containing relevance_score and retry_count

    Returns:
        "generate" if relevance is above threshold or retry limit reached,
        "rewrite_retry" otherwise
    """
    if state["relevance_score"] >= _RELEVANCE_THRESHOLD or state["retry_count"] >= _MAX_GRADE_RETRIES:
        return "generate"
    return "rewrite_retry"


def route_after_hallucination(state: dict) -> str:
    """Route after hallucination check.

    Args:
        state: Graph state containing hallucination_passed and retry_count

    Returns:
        "save_memory" if hallucination check passed or retry limit reached,
        "generate" otherwise
    """
    if state["hallucination_passed"] or state["retry_count"] >= _MAX_TOTAL_RETRIES:
        return "save_memory"
    return "generate"


def route_after_router(state: dict) -> str:
    """Route based on router decision and rewrite strategy.

    Args:
        state: Graph state containing route and rewrite_strategy fields

    Returns:
        "clarify" if clarify route,
        "multi_query" if doc_search route with multi_query strategy,
        otherwise the route value from state
    """
    route = state["route"]
    if route == "clarify":
        return "clarify"
    if route == "doc_search" and state.get("rewrite_strategy") == "multi_query":
        return "multi_query"
    return route


def route_after_agent(state: dict) -> str:
    """에이전트 응답에 도구 호출이 있으면 게이트로, 없으면 최종 답변 노드로 (ADR-0023, ADR-0031 라벨=노드명)."""
    messages = state.get("agent_messages") or []
    for m in reversed(messages):
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls is not None:
            return "tool_gate" if tool_calls else "agent_answer"
    return "agent_answer"


def route_after_tool_gate(state: dict) -> str:
    """JUSTIFY 대기 호출이 있으면 confirm(HITL), 직접 답변이 설정됐으면 agent_answer,
    없으면 에이전트로 복귀 (ADR-0023)."""
    if state.get("pending_tool_calls"):
        return "confirm"
    if state.get("answer"):
        return "agent_answer"
    return "agent"

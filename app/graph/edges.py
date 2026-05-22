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
        "end" if hallucination check passed or retry limit reached,
        "generate" otherwise
    """
    if state["hallucination_passed"] or state["retry_count"] >= _MAX_TOTAL_RETRIES:
        return "end"
    return "generate"


def route_after_router(state: dict) -> str:
    """Route based on router decision.

    Args:
        state: Graph state containing route field

    Returns:
        The route value from state (e.g., "doc_search", "web_search", "tool_call")
    """
    return state["route"]


def route_after_confirm(state: dict) -> str:
    """Route based on user confirmation.

    Args:
        state: Graph state containing confirmed flag

    Returns:
        "tool_executor" if confirmed is True, "end" otherwise
    """
    return "tool_executor" if state["confirmed"] else "end"

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
        "multi_query" if doc_search route with multi_query strategy,
        otherwise the route value from state
    """
    route = state["route"]
    if route == "doc_search" and state.get("rewrite_strategy") == "multi_query":
        return "multi_query"
    return route


def route_after_gate(state: dict) -> str:
    """Route based on the identity×risk gate decision (ADR-0016).

    Returns:
        "sql_execute" for ALLOW, "confirm" for NEEDS_APPROVAL, "sql_reject" for DENY.
    """
    decision = state["gate_decision"]
    if decision == "ALLOW":
        return "sql_execute"
    if decision == "NEEDS_APPROVAL":
        return "confirm"
    return "sql_reject"


def route_after_confirm(state: dict) -> str:
    """Route after NEEDS_APPROVAL human confirmation (ADR-0016).

    Returns:
        "sql_execute" if confirmed, "sql_reject" otherwise (user cancelled).
    """
    return "sql_execute" if state["confirmed"] else "sql_reject"

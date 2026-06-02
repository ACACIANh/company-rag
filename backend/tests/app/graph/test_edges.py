from app.graph.edges import route_after_confirm, route_after_gate, route_after_grade, route_after_hallucination, route_after_router


# ─── route_after_grade ───

def test_route_after_grade_goes_to_generate_when_score_high():
    state = {"relevance_score": 0.8, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_goes_to_generate_at_threshold():
    state = {"relevance_score": 0.5, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_retries_when_score_low_and_count_below_limit():
    state = {"relevance_score": 0.3, "retry_count": 0}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_retries_once_more_at_count_1():
    state = {"relevance_score": 0.1, "retry_count": 1}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_forces_generate_when_retry_limit_reached():
    state = {"relevance_score": 0.0, "retry_count": 2}
    assert route_after_grade(state) == "generate"


# ─── route_after_hallucination ───

def test_route_after_hallucination_goes_to_save_memory_when_passed():
    state = {"hallucination_passed": True, "retry_count": 0}
    assert route_after_hallucination(state) == "save_memory"


def test_route_after_hallucination_retries_when_failed_and_count_below_limit():
    state = {"hallucination_passed": False, "retry_count": 0}
    assert route_after_hallucination(state) == "generate"


def test_route_after_hallucination_goes_to_save_memory_when_retry_limit_reached():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "save_memory"


def test_route_after_hallucination_goes_to_save_memory_after_max_retries():
    # grade 2회 + hallucination 1회 → retry_count=3 → save_memory
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "save_memory"


# ─── route_after_router ───

def test_route_after_router_returns_doc_search():
    assert route_after_router({"route": "doc_search"}) == "doc_search"


def test_route_after_router_returns_tool_call():
    assert route_after_router({"route": "tool_call"}) == "tool_call"


def test_route_after_router_returns_multi_query_when_strategy_set():
    state = {"route": "doc_search", "rewrite_strategy": "multi_query"}
    assert route_after_router(state) == "multi_query"


def test_route_after_router_returns_doc_search_when_strategy_none():
    state = {"route": "doc_search", "rewrite_strategy": "none"}
    assert route_after_router(state) == "doc_search"


def test_route_after_router_returns_doc_search_when_no_strategy_key():
    """rewrite_strategy 키가 없어도 기존 동작 유지."""
    state = {"route": "doc_search"}
    assert route_after_router(state) == "doc_search"


# ─── route_after_confirm (SQL 게이트 NEEDS_APPROVAL 전용) ───

def test_route_after_confirm_executes_when_confirmed():
    assert route_after_confirm({"confirmed": True}) == "sql_execute"


def test_route_after_confirm_rejects_when_denied():
    assert route_after_confirm({"confirmed": False}) == "sql_reject"


# ─── route_after_gate (ADR-0016 3-state) ───

def test_route_after_gate_allow_executes():
    assert route_after_gate({"gate_decision": "ALLOW"}) == "sql_execute"


def test_route_after_gate_needs_approval_confirms():
    assert route_after_gate({"gate_decision": "NEEDS_APPROVAL"}) == "confirm"


def test_route_after_gate_deny_rejects():
    assert route_after_gate({"gate_decision": "DENY"}) == "sql_reject"

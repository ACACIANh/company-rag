from langchain_core.messages import AIMessage
from app.graph.edges import route_after_grade, route_after_hallucination, route_after_router, route_after_agent, route_after_tool_gate


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


def test_route_after_router_returns_agent():
    assert route_after_router({"route": "agent"}) == "agent"


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


# ─── route_after_agent / route_after_tool_gate (ADR-0023) ───

def test_route_after_agent_to_tool_gate_when_tool_calls():
    ai = AIMessage(content="", tool_calls=[{"name": "query_business_data", "args": {}, "id": "c1"}])
    assert route_after_agent({"agent_messages": [ai]}) == "tool_gate"


def test_route_after_agent_to_answer_when_no_tool_calls():
    ai = AIMessage(content="최종 답변")
    assert route_after_agent({"agent_messages": [ai]}) == "agent_answer"


def test_route_after_tool_gate_to_confirm_when_pending():
    assert route_after_tool_gate({"pending_tool_calls": [{"id": "c1"}]}) == "confirm"


def test_route_after_tool_gate_back_to_agent_when_no_pending():
    assert route_after_tool_gate({"pending_tool_calls": []}) == "agent"

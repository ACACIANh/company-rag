from typing import get_type_hints, get_origin
from app.graph.state import AgentState


def test_agent_state_has_required_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    required = {"question", "documents", "answer", "citations",
                "chat_history", "retry_count", "relevance_score",
                "hallucination_passed", "rewritten_question", "route"}
    assert required.issubset(hints.keys())


def test_agent_state_instantiation():
    state: AgentState = {
        "question": "테스트",
        "rewritten_question": "",
        "chat_history": [],
        "route": "doc_search",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
    }
    assert state["question"] == "테스트"


def test_documents_is_plain_list_not_annotated():
    hints = get_type_hints(AgentState, include_extras=True)
    doc_hint = hints["documents"]
    # Annotated[..., add]가 아닌 순수 list 타입이어야 함
    assert get_origin(doc_hint) is list or doc_hint is list or str(doc_hint).startswith("list")


def test_agent_state_has_phase3_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "confirmed" in hints
    assert "tool_input" in hints


def test_agent_state_phase3_instantiation():
    state: AgentState = {
        "question": "회의실 예약해줘",
        "rewritten_question": "회의실 예약 요청",
        "chat_history": [],
        "route": "agent",
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "회의실 A, 2026-06-01 14:00",
    }
    assert state["confirmed"] is False
    assert state["tool_input"] == "회의실 A, 2026-06-01 14:00"


def test_agent_state_has_justification_field():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "justification" in hints   # ADR-0027


def test_agent_state_has_multi_query_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "rewrite_strategy" in hints
    assert "multi_queries" in hints


def test_agent_state_multi_query_instantiation():
    state: AgentState = {
        "question": "연차 vs 병가 비교",
        "rewritten_question": "연차와 병가의 차이점은?",
        "chat_history": [],
        "route": "doc_search",
        "rewrite_strategy": "multi_query",
        "multi_queries": ["연차 규정은?", "병가 규정은?"],
        "documents": [],
        "relevance_score": 0.0,
        "retry_count": 0,
        "answer": "",
        "citations": [],
        "hallucination_passed": False,
        "confirmed": False,
        "tool_input": "",
        "user_id": "u1",
        "allowed_folders": [],
    }
    assert state["rewrite_strategy"] == "multi_query"
    assert state["multi_queries"] == ["연차 규정은?", "병가 규정은?"]


def test_agent_state_has_agentic_loop_fields():
    hints = get_type_hints(AgentState, include_extras=True)
    assert "agent_messages" in hints      # ADR-0023
    assert "pending_tool_calls" in hints   # ADR-0023

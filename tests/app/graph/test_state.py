from typing import get_type_hints
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

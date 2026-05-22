from typing import get_type_hints, get_args, get_origin
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

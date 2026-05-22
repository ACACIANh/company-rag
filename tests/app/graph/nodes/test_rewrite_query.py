from unittest.mock import MagicMock

from app.graph.nodes.rewrite_query import rewrite_query_node


def test_rewrite_query_returns_rewritten_question():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "재작성된 질문"

    state = {"question": "그거 어떻게 해?"}
    result = rewrite_query_node(state, llm=mock_llm)

    assert result == {"rewritten_question": "재작성된 질문"}


def test_rewrite_query_strips_whitespace():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  연차 신청 방법  \n"

    state = {"question": "연차 어떻게 써?"}
    result = rewrite_query_node(state, llm=mock_llm)

    assert result["rewritten_question"] == "연차 신청 방법"


def test_rewrite_query_includes_original_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "재작성"

    rewrite_query_node({"question": "원본 질문"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt

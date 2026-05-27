from unittest.mock import MagicMock

from app.graph.nodes.multi_query import multi_query_node


def test_multi_query_returns_list_of_queries():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "연차 신청 방법\n연차 일수 정책\n연차 신청 기한"

    result = multi_query_node({"rewritten_question": "연차 관련 정책 전부 알려줘"}, llm=mock_llm)

    assert "multi_queries" in result
    assert len(result["multi_queries"]) == 3
    assert result["multi_queries"][0] == "연차 신청 방법"


def test_multi_query_strips_whitespace_from_each_query():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  병가 신청 절차  \n  병가 최대 일수  "

    result = multi_query_node({"rewritten_question": "병가 관련 알려줘"}, llm=mock_llm)

    assert result["multi_queries"] == ["병가 신청 절차", "병가 최대 일수"]


def test_multi_query_caps_at_three_queries():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "q1\nq2\nq3\nq4\nq5"

    result = multi_query_node({"rewritten_question": "복잡한 질문"}, llm=mock_llm)

    assert len(result["multi_queries"]) == 3


def test_multi_query_falls_back_to_original_on_empty_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "   "

    result = multi_query_node({"rewritten_question": "연차 정책"}, llm=mock_llm)

    assert result["multi_queries"] == ["연차 정책"]


def test_multi_query_uses_rewritten_question_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1"

    multi_query_node({"rewritten_question": "재작성된 질문 내용"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "재작성된 질문 내용" in prompt


def test_multi_query_falls_back_to_question_when_no_rewritten():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1"

    multi_query_node({"question": "원본 질문", "rewritten_question": ""}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "원본 질문" in prompt


def test_multi_query_ignores_empty_lines():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "쿼리1\n\n쿼리2\n\n"

    result = multi_query_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["multi_queries"] == ["쿼리1", "쿼리2"]

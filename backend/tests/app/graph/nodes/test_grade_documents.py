from unittest.mock import MagicMock

from core.models import Chunk, SearchResult
from app.graph.nodes.grade_documents import grade_documents_node


def _make_result(text: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source="a.md", chunk_id="c1"), score=0.9)


def test_grade_documents_returns_float_score():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "0.8"

    state = {
        "rewritten_question": "연차 신청 방법",
        "documents": [_make_result("연차는 15일입니다.")],
    }
    result = grade_documents_node(state, llm=mock_llm)

    assert "relevance_score" in result
    assert abs(result["relevance_score"] - 0.8) < 1e-6


def test_grade_documents_falls_back_to_zero_on_invalid_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "잘 모르겠어요"

    state = {
        "rewritten_question": "질문",
        "documents": [_make_result("내용")],
    }
    result = grade_documents_node(state, llm=mock_llm)

    assert result["relevance_score"] == 0.0


def test_grade_documents_empty_documents_returns_zero():
    mock_llm = MagicMock()

    state = {"rewritten_question": "질문", "documents": []}
    result = grade_documents_node(state, llm=mock_llm)

    assert result["relevance_score"] == 0.0
    mock_llm.complete.assert_not_called()


def test_grade_documents_includes_question_and_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "0.9"

    state = {
        "rewritten_question": "검색 질문",
        "documents": [_make_result("핵심 문서 내용")],
    }
    grade_documents_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "검색 질문" in prompt
    assert "핵심 문서 내용" in prompt

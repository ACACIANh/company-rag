from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.check_hallucination import check_hallucination_node


def _make_result(text: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source="a.md", chunk_id="c1"), score=0.9)


def test_check_hallucination_passes_when_llm_says_yes():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "YES"

    state = {
        "answer": "연차는 15일입니다.",
        "documents": [_make_result("연차는 15일입니다.")],
        "retry_count": 0,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is True
    assert "retry_count" not in result


def test_check_hallucination_fails_when_llm_says_no_and_increments_retry():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "NO"

    state = {
        "answer": "임의의 답변",
        "documents": [_make_result("다른 내용")],
        "retry_count": 1,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is False
    assert result["retry_count"] == 2


def test_check_hallucination_is_case_insensitive():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "yes, this answer is grounded"

    state = {
        "answer": "답변",
        "documents": [_make_result("근거")],
        "retry_count": 0,
    }
    result = check_hallucination_node(state, llm=mock_llm)

    assert result["hallucination_passed"] is True


def test_check_hallucination_includes_answer_and_context_in_prompt():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "YES"

    state = {
        "answer": "검증 대상 답변",
        "documents": [_make_result("참조 문서")],
        "retry_count": 0,
    }
    check_hallucination_node(state, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "검증 대상 답변" in prompt
    assert "참조 문서" in prompt

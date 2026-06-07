from core.models import Chunk, SearchResult
from app.graph.nodes.grade_documents import grade_documents_node


def _result(score: float, text: str = "내용") -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source="a.md", chunk_id="c1"), score=score)


def test_grade_documents_above_threshold_is_relevant():
    """최상위 문서 cosine이 임계 이상이면 관련(1.0). LLM 없이 동작(순수 함수)."""
    state = {"rewritten_question": "연차 신청 방법", "documents": [_result(0.50)]}
    result = grade_documents_node(state)
    assert result["relevance_score"] == 1.0


def test_grade_documents_below_threshold_is_irrelevant():
    """최상위 cosine이 임계 미만이면 비관련(0.0) → rewrite_retry/거부 경로."""
    state = {"rewritten_question": "질문", "documents": [_result(0.30)]}
    result = grade_documents_node(state)
    assert result["relevance_score"] == 0.0


def test_grade_documents_at_threshold_is_relevant():
    """경계값(임계와 동일)은 관련으로 본다(>= 비교)."""
    state = {"rewritten_question": "질문", "documents": [_result(0.35)]}
    result = grade_documents_node(state)
    assert result["relevance_score"] == 1.0


def test_grade_documents_uses_max_score_not_first():
    """reranker가 순서를 바꿔도 견고하게: 문서 중 최대 cosine으로 판정한다."""
    # 첫 문서는 임계 미만이지만 더 관련 높은 문서가 뒤에 있음 → 관련
    state = {"rewritten_question": "질문", "documents": [_result(0.20), _result(0.60)]}
    result = grade_documents_node(state)
    assert result["relevance_score"] == 1.0


def test_grade_documents_empty_documents_returns_zero():
    state = {"rewritten_question": "질문", "documents": []}
    result = grade_documents_node(state)
    assert result["relevance_score"] == 0.0

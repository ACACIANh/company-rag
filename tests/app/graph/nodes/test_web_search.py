from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.web_search import web_search_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id=source), score=0.5)


def test_web_search_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result("검색 결과", "https://example.com")]

    state = {"rewritten_question": "LangGraph 최신 버전", "question": "LangGraph 버전 알려줘"}
    result = web_search_node(state, retriever=mock_retriever)

    assert "documents" in result
    assert len(result["documents"]) == 1
    assert result["documents"][0].chunk.text == "검색 결과"


def test_web_search_node_uses_rewritten_question():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    web_search_node(
        {"rewritten_question": "재작성 질문", "question": "원본 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("재작성 질문", top_k=5)


def test_web_search_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    web_search_node(
        {"rewritten_question": "", "question": "원본 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("원본 질문", top_k=5)


def test_web_search_node_returns_empty_list_when_no_results():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    result = web_search_node(
        {"rewritten_question": "질문", "question": "질문"},
        retriever=mock_retriever,
    )

    assert result["documents"] == []

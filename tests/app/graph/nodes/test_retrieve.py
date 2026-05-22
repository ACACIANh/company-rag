from unittest.mock import MagicMock

from shared.models import Chunk, SearchResult
from app.graph.nodes.retrieve import retrieve_node


def _make_result(text: str, source: str) -> SearchResult:
    return SearchResult(chunk=Chunk(text=text, source=source, chunk_id="test-1"), score=0.9)


def test_retrieve_node_returns_documents():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [_make_result("내용", "doc.md")]

    state = {"question": "테스트 질문"}
    result = retrieve_node(state, retriever=mock_retriever)

    assert "documents" in result
    assert len(result["documents"]) == 1
    mock_retriever.retrieve.assert_called_once_with("테스트 질문", top_k=5)


def test_retrieve_node_uses_question_field():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node({"question": "특정 질문"}, retriever=mock_retriever)
    mock_retriever.retrieve.assert_called_once_with("특정 질문", top_k=5)


def test_retrieve_node_uses_rewritten_question_when_available():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": "재작성 질문"},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("재작성 질문", top_k=5)


def test_retrieve_node_falls_back_to_question_when_rewritten_empty():
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    retrieve_node(
        {"question": "원본 질문", "rewritten_question": ""},
        retriever=mock_retriever,
    )

    mock_retriever.retrieve.assert_called_once_with("원본 질문", top_k=5)

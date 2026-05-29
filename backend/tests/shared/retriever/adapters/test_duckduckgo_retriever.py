from unittest.mock import MagicMock, patch

from shared.retriever.adapters.duckduckgo_retriever import DuckDuckGoRetriever


def _make_ddg_result(body: str, href: str) -> dict:
    return {"body": body, "href": href, "title": "제목"}


def test_duckduckgo_retriever_returns_search_results():
    mock_results = [
        _make_ddg_result("LangGraph 설명", "https://example.com/1"),
        _make_ddg_result("LangGraph 튜토리얼", "https://example.com/2"),
    ]
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = mock_results
        MockDDGS.return_value = mock_ddgs

        retriever = DuckDuckGoRetriever()
        results = retriever.retrieve("LangGraph", top_k=5)

    assert len(results) == 2
    assert results[0].chunk.text == "LangGraph 설명"
    assert results[0].chunk.source == "https://example.com/1"
    assert results[0].score == 0.5


def test_duckduckgo_retriever_respects_top_k():
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = []
        MockDDGS.return_value = mock_ddgs

        DuckDuckGoRetriever().retrieve("질문", top_k=3)

        mock_ddgs.text.assert_called_once_with("질문", max_results=3)


def test_duckduckgo_retriever_returns_empty_on_no_results():
    with patch("shared.retriever.adapters.duckduckgo_retriever.DDGS") as MockDDGS:
        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = []
        MockDDGS.return_value = mock_ddgs

        results = DuckDuckGoRetriever().retrieve("질문", top_k=5)

    assert results == []

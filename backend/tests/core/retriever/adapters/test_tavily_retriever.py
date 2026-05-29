from unittest.mock import MagicMock, patch

from core.retriever.adapters.tavily_retriever import TavilyRetriever


async def test_tavily_retriever_returns_search_results():
    mock_response = {
        "results": [
            {"content": "LangGraph 최신 기능 설명", "url": "https://example.com/1", "score": 0.9},
            {"content": "LangGraph 튜토리얼", "url": "https://example.com/2", "score": 0.8},
        ]
    }
    with patch("core.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = await retriever.retrieve("LangGraph 업데이트", top_k=5)

    assert len(results) == 2
    assert results[0].chunk.text == "LangGraph 최신 기능 설명"
    assert results[0].chunk.source == "https://example.com/1"
    assert abs(results[0].score - 0.9) < 1e-6


async def test_tavily_retriever_respects_top_k():
    mock_response = {"results": []}
    with patch("core.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        await retriever.retrieve("질문", top_k=3)

        mock_client.search.assert_called_once_with("질문", max_results=3)


async def test_tavily_retriever_returns_empty_on_no_results():
    mock_response = {"results": []}
    with patch("core.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = await retriever.retrieve("질문", top_k=5)

    assert results == []


async def test_tavily_retriever_uses_default_score_when_missing():
    mock_response = {
        "results": [{"content": "내용", "url": "https://example.com"}]
    }
    with patch("core.retriever.adapters.tavily_retriever.TavilyClient") as MockClient:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        MockClient.return_value = mock_client

        retriever = TavilyRetriever(api_key="test-key")
        results = await retriever.retrieve("질문", top_k=5)

    assert results[0].score == 0.5

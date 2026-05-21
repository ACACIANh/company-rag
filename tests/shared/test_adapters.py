import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from shared.llm.adapters.langchain_adapter import LangChainLLMAdapter
from shared.vector_store.adapters.langchain_retriever import LangChainRetrieverAdapter
from shared.models import Chunk, SearchResult


def test_langchain_llm_adapter_generates(mocker):
    mock_client = MagicMock()
    mock_client.complete.return_value = "테스트 답변"

    adapter = LangChainLLMAdapter(llm_client=mock_client)
    result = adapter.invoke("테스트 프롬프트")

    mock_client.complete.assert_called_once_with("테스트 프롬프트")
    assert "테스트 답변" in result


def test_langchain_retriever_adapter_returns_documents():
    mock_store = MagicMock()
    mock_store.search.return_value = [
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.1, 0.2, 0.3]

    adapter = LangChainRetrieverAdapter(
        vector_store=mock_store, embedding_service=mock_embedder
    )
    docs = adapter.invoke("연차 며칠이야")

    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert docs[0].page_content == "연차 15일"
    assert docs[0].metadata["source"] == "vacation.md"

# tests/shared/test_retriever.py
import pytest
from unittest.mock import MagicMock
from shared.models import Chunk, SearchResult
from shared.retriever.retriever import Retriever


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.search.return_value = [
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ]
    return store


@pytest.fixture
def mock_embedder():
    embedder = MagicMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]
    return embedder


def test_retriever_calls_embed_and_search(mock_store, mock_embedder):
    retriever = Retriever(vector_store=mock_store, embedding_service=mock_embedder)

    results = retriever.retrieve("연차 며칠이야", top_k=3)

    mock_embedder.embed.assert_called_once_with("연차 며칠이야")
    mock_store.search.assert_called_once_with([0.1, 0.2, 0.3], top_k=3)
    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"

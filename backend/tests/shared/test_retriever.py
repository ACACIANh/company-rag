from unittest.mock import AsyncMock, MagicMock

from shared.models import Chunk, SearchResult
from shared.retriever import BasicRetriever
from shared.retriever.base import Retriever


def test_basic_retriever_implements_abc():
    assert issubclass(BasicRetriever, Retriever)


async def test_basic_retriever_calls_embed_and_search():
    store = AsyncMock()
    store.search = AsyncMock(return_value=[
        SearchResult(
            chunk=Chunk(text="연차 15일", source="vacation.md", chunk_id="c1"),
            score=0.9,
        )
    ])
    embedder = MagicMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]

    r = BasicRetriever(store=store, embedder=embedder)
    results = await r.retrieve("연차 며칠이야", top_k=3)

    embedder.embed.assert_called_once_with("연차 며칠이야")
    store.search.assert_called_once_with([0.1, 0.2, 0.3], top_k=3, where_clause="", params=None)
    assert len(results) == 1
    assert results[0].chunk.source == "vacation.md"


async def test_basic_retriever_empty_results():
    store = AsyncMock()
    store.search = AsyncMock(return_value=[])
    embedder = MagicMock()
    embedder.embed.return_value = [0.0]
    r = BasicRetriever(store=store, embedder=embedder)
    assert await r.retrieve("anything") == []

from unittest.mock import AsyncMock, MagicMock

from core.models import Chunk, SearchResult
from core.retriever import BasicRetriever
from core.retriever.base import Retriever


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


async def test_basic_retriever_retrieve_batch_embeds_once_and_searches_per_query():
    """multi_query 최적화: 여러 쿼리를 embed_batch 1회로 묶고 검색은 쿼리별 1회씩.

    동작 보존 — 쿼리별 임베딩은 단건 embed와 동일(배치는 결과 불변), 반환은 쿼리별 리스트.
    """
    store = AsyncMock()
    store.search = AsyncMock(side_effect=[
        [SearchResult(chunk=Chunk(text="r1", source="a.md", chunk_id="c1"), score=0.9)],
        [SearchResult(chunk=Chunk(text="r2", source="b.md", chunk_id="c2"), score=0.8)],
    ])
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

    r = BasicRetriever(store=store, embedder=embedder)
    results = await r.retrieve_batch(["q1", "q2"], top_k=3, where_clause="wc", params=[1])

    # 임베딩은 배치 1회 — 단건 embed는 호출되지 않는다
    embedder.embed_batch.assert_called_once_with(["q1", "q2"])
    embedder.embed.assert_not_called()
    # 검색은 임베딩별 1회씩, 각 임베딩을 그대로 사용
    assert store.search.call_count == 2
    assert store.search.call_args_list[0].args[0] == [0.1, 0.2]
    assert store.search.call_args_list[1].args[0] == [0.3, 0.4]
    # 반환은 쿼리별 결과 리스트(순서 보존)
    assert len(results) == 2
    assert results[0][0].chunk.source == "a.md"
    assert results[1][0].chunk.source == "b.md"


async def test_retriever_abc_retrieve_batch_defaults_to_per_query_retrieve():
    """embed_batch가 없는 Retriever(웹 검색 어댑터 등)도 안전: 기본 구현은 per-query retrieve."""

    class _SeqRetriever(Retriever):
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def retrieve(self, query, top_k=5, where_clause="", params=None):
            self.calls.append(query)
            return [SearchResult(
                chunk=Chunk(text=query, source=f"{query}.md", chunk_id=query), score=1.0,
            )]

    r = _SeqRetriever()
    results = await r.retrieve_batch(["x", "y"], top_k=2)

    assert r.calls == ["x", "y"]
    assert [lst[0].chunk.source for lst in results] == ["x.md", "y.md"]

import asyncio

from core.fga.client import FGAClient
from core.models import SearchResult
from core.reranker.base import Reranker
from core.retriever.base import Retriever


def _rrf_merge(ranked_lists: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    """Reciprocal Rank Fusion — 여러 ranked list를 하나로 병합."""
    rrf_scores: dict[str, float] = {}
    best_result: dict[str, SearchResult] = {}
    for ranked_list in ranked_lists:
        for rank, result in enumerate(ranked_list, start=1):
            key = result.chunk.chunk_id
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in best_result:
                best_result[key] = result
    return sorted(
        best_result.values(),
        key=lambda r: rrf_scores[r.chunk.chunk_id],
        reverse=True,
    )


async def retrieve_node(
    state: dict,
    *,
    retriever: Retriever,
    fga_client: FGAClient,
    reranker: Reranker | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> dict:
    where_clause, params = fga_client.build_pg_filter(state.get("allowed_folders", []))

    multi_queries: list[str] = state.get("multi_queries") or []

    if multi_queries:
        all_results = await asyncio.gather(*[
            retriever.retrieve(q, top_k=retrieve_top_k, where_clause=where_clause, params=params)
            for q in multi_queries
        ])
        results = _rrf_merge(list(all_results))
        primary_query = multi_queries[0]
    else:
        primary_query = state.get("rewritten_question") or state["question"]
        results = await retriever.retrieve(
            primary_query, top_k=retrieve_top_k, where_clause=where_clause, params=params
        )

    # 기본 구현체 선택은 합성 루트(builder)의 책임 — 노드는 core 구현체를 직접 참조하지 않는다.
    # reranker 미주입이면 reranking 없이 상위 top_k만 순서 보존(NoOpReranker와 동일).
    if reranker is not None:
        reranked = reranker.rerank(primary_query, results, top_k=top_k)
    else:
        reranked = list(results[:top_k])
    return {"documents": reranked}

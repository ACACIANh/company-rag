from core.models import SearchResult
from core.reranker.base import Reranker
from core.retriever.base import Retriever


class RRFReranker(Reranker):
    """Reciprocal Rank Fusion — dense + sparse 두 ranked list를 합산해 재정렬.

    score(d) = Σ_i  1 / (k + rank_i(d))

    Hybrid Search 미도입 시에도 secondary_retriever에 동일 retriever를 넣으면
    단일 리스트 RRF로 동작한다 (사실상 NoOp).
    """

    def __init__(
        self,
        secondary_retriever: Retriever,
        k: int = 60,
        secondary_top_k: int = 20,
    ) -> None:
        self._secondary = secondary_retriever
        self._k = k
        self._secondary_top_k = secondary_top_k

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        secondary = self._secondary.retrieve(query, top_k=self._secondary_top_k)
        fused = self._fuse([results, secondary])
        return fused[:top_k] if top_k is not None else fused

    def _fuse(self, ranked_lists: list[list[SearchResult]]) -> list[SearchResult]:
        rrf_scores: dict[str, float] = {}
        best_result: dict[str, SearchResult] = {}

        for ranked_list in ranked_lists:
            for rank, result in enumerate(ranked_list, start=1):
                key = result.chunk.chunk_id
                rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (self._k + rank)
                if key not in best_result:
                    best_result[key] = result

        return sorted(
            best_result.values(),
            key=lambda r: rrf_scores[r.chunk.chunk_id],
            reverse=True,
        )

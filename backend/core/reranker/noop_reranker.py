from shared.models import SearchResult
from shared.reranker.base import Reranker


class NoOpReranker(Reranker):
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        if top_k is None:
            return list(results)
        return list(results[:top_k])

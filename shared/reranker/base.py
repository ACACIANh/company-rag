from abc import ABC, abstractmethod

from shared.models import SearchResult


class Reranker(ABC):
    @abstractmethod
    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]: ...

from abc import ABC, abstractmethod

from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 5, where_filter: dict | None = None
    ) -> list[SearchResult]: ...

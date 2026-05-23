from abc import ABC, abstractmethod

from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 5, filter_doc_ids: list[str] | None = None
    ) -> list[SearchResult]: ...

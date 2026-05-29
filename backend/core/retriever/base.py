from abc import ABC, abstractmethod
from shared.models import SearchResult


class Retriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]: ...

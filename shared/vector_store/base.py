from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    async def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None: ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]: ...

    @abstractmethod
    async def count(self) -> int: ...

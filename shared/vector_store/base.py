from abc import ABC, abstractmethod
from shared.models import Chunk, SearchResult


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        ...

    @abstractmethod
    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

from shared.models import SearchResult
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.base import VectorStore


class Retriever:
    def __init__(
        self, vector_store: VectorStore, embedding_service: EmbeddingService
    ) -> None:
        self._store = vector_store
        self._embedder = embedding_service

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k)

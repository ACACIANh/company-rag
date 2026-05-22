from shared.embedder.base import Embedder
from shared.models import SearchResult
from shared.retriever.base import Retriever
from shared.vector_store.base import VectorStore


class BasicRetriever(Retriever):
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    def retrieve(
        self, query: str, top_k: int = 5, filter_doc_ids: list[str] | None = None
    ) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k, filter_doc_ids=filter_doc_ids)

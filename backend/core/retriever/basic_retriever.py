from core.embedder.base import Embedder
from core.models import SearchResult
from core.retriever.base import Retriever
from core.vector_store.base import VectorStore


class BasicRetriever(Retriever):
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[SearchResult]:
        embedding = self._embedder.embed(query)
        return await self._store.search(
            embedding, top_k=top_k, where_clause=where_clause, params=params
        )

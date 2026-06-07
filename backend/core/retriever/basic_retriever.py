import asyncio

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

    async def retrieve_batch(
        self,
        queries: list[str],
        top_k: int = 5,
        where_clause: str = "",
        params: list | None = None,
    ) -> list[list[SearchResult]]:
        # 임베딩을 배치 1회로 묶어 왕복을 N→1로 줄인다(동기 호출은 스레드로 이벤트루프 비차단).
        # 결과는 쿼리별 단건 embed와 동일 — 검색만 임베딩별 병렬.
        embeddings = await asyncio.to_thread(self._embedder.embed_batch, list(queries))
        return list(await asyncio.gather(*(
            self._store.search(emb, top_k=top_k, where_clause=where_clause, params=params)
            for emb in embeddings
        )))

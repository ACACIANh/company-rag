import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class QdrantStore(VectorStore):
    def __init__(self, url: str, api_key: str, collection: str) -> None:
        self._client = QdrantClient(url=url, api_key=api_key)
        self._collection = collection

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=len(embeddings[0]), distance=Distance.COSINE
                ),
            )
        points = [
            PointStruct(
                id=uuid.uuid5(uuid.NAMESPACE_DNS, c.chunk_id),
                vector=emb,
                payload={"text": c.text, "source": c.source, "chunk_id": c.chunk_id},
            )
            for c, emb in zip(chunks, embeddings)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def search(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[SearchResult]:
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=query_embedding,
            limit=top_k,
        )
        return [
            SearchResult(
                chunk=Chunk(
                    text=h.payload["text"],
                    source=h.payload["source"],
                    chunk_id=h.payload["chunk_id"],
                ),
                score=h.score,
            )
            for h in hits
        ]

    def count(self) -> int:
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            return 0
        return self._client.count(collection_name=self._collection).count

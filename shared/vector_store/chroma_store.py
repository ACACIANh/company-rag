import chromadb
from shared.models import Chunk, SearchResult
from shared.vector_store.base import VectorStore


class ChromaStore(VectorStore):
    def __init__(
        self,
        path: str,
        mode: str = "embedded",
        host: str = "localhost",
        port: int = 8000,
    ) -> None:
        if mode == "http":
            self._client = chromadb.HttpClient(host=host, port=port)
        else:
            self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection("documents")

    def add(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        extra_metadata: list[dict] | None = None,
    ) -> None:
        metadatas = []
        for i, c in enumerate(chunks):
            meta = {"source": c.source}
            if extra_metadata and i < len(extra_metadata):
                meta.update(extra_metadata[i])
            metadatas.append(meta)
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where_filter: dict | None = None,
    ) -> list[SearchResult]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self._collection.count(), 1)),
            where=where_filter,
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            chunk = Chunk(
                text=doc,
                source=meta["source"],
                chunk_id=results["ids"][0][i],
                metadata=meta,
            )
            score = 1.0 - results["distances"][0][i]
            output.append(SearchResult(chunk=chunk, score=score))
        return output

    def count(self) -> int:
        return self._collection.count()

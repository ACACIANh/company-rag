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

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[{"source": c.source} for c in chunks],
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filter_doc_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        where = None
        if filter_doc_ids:
            where = {"source": {"$in": filter_doc_ids}}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(self._collection.count(), 1)),
            where=where,
        )
        output = []
        for i, doc in enumerate(results["documents"][0]):
            chunk = Chunk(
                text=doc,
                source=results["metadatas"][0][i]["source"],
                chunk_id=results["ids"][0][i],
            )
            score = 1.0 - results["distances"][0][i]
            output.append(SearchResult(chunk=chunk, score=score))
        return output

    def count(self) -> int:
        return self._collection.count()

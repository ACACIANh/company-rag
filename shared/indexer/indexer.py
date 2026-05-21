import os
import uuid
from shared.models import Chunk
from shared.retriever.embedding import EmbeddingService
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self._store = vector_store
        self._embedder = embedding_service
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def index_directory(self, docs_path: str) -> int:
        chunks = []
        for filename in sorted(os.listdir(docs_path)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(docs_path, filename)
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            chunks.extend(self._chunk_text(content, filename))

        if not chunks:
            return 0

        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        self._store.add(chunks, embeddings)
        return len(chunks)

    def _chunk_text(self, text: str, source: str) -> list[Chunk]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        source=source,
                        chunk_id=str(uuid.uuid4()),
                    )
                )
            start += self._chunk_size - self._chunk_overlap
        return chunks

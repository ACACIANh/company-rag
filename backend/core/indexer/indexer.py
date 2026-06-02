from core.chunker.base import Chunker
from core.document_original.base import DocumentOriginalStore
from core.embedder.base import Embedder
from core.loader.base import DocumentLoader
from core.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        original_store: DocumentOriginalStore | None = None,
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._original_store = original_store

    async def index(self, path: str) -> int:
        docs = self._loader.load(path)
        if self._original_store is not None:
            for d in docs:
                if d.raw is not None and d.mime is not None:
                    folder_path = d.metadata.get("path", "")
                    filename = d.source.rsplit("/", 1)[-1]
                    await self._original_store.save(
                        folder_path + "/" + filename, folder_path, filename, d.mime, d.raw
                    )
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        await self._store.add(chunks, embeddings)
        return len(chunks)

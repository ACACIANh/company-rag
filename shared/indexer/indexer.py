from shared.chunker.base import Chunker
from shared.embedder.base import Embedder
from shared.fga.sensitivity import detect_sensitivity
from shared.loader.base import DocumentLoader
from shared.vector_store.base import VectorStore


class Indexer:
    def __init__(
        self,
        loader: DocumentLoader,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        fga_client=None,   # FGAClient | None — 순환 import 방지로 타입 미지정
        default_team_id: str = "team:general",
        default_owner_id: str = "user:system",
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._fga_client = fga_client
        self._default_team_id = default_team_id
        self._default_owner_id = default_owner_id

    def index(self, path: str) -> int:
        docs = self._loader.load(path)
        chunks = [c for d in docs for c in self._chunker.chunk(d)]
        if not chunks:
            return 0
        embeddings = self._embedder.embed_batch([c.text for c in chunks])

        doc_metadata: dict[str, dict] = {}
        for c in chunks:
            if c.source not in doc_metadata:
                full_text = " ".join(ch.text for ch in chunks if ch.source == c.source)
                sensitivity = detect_sensitivity(full_text)
                doc_metadata[c.source] = {
                    "document_id": f"doc:{c.source}",
                    "team_id": self._default_team_id,
                    "sensitivity": sensitivity,
                }

        extra_metadata = [doc_metadata[c.source] for c in chunks]
        self._store.add(chunks, embeddings, extra_metadata=extra_metadata)

        if self._fga_client:
            for source, meta in doc_metadata.items():
                self._fga_client.write_tuples(
                    doc_id=meta["document_id"],
                    owner_id=self._default_owner_id,
                    team_id=meta["team_id"],
                    sensitivity=meta["sensitivity"],
                )
        return len(chunks)

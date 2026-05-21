import uuid

from shared.chunker.base import Chunker
from shared.models import Chunk, Document


class FixedSizeChunker(Chunker):
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self._size = chunk_size
        self._overlap = chunk_overlap

    def chunk(self, doc: Document) -> list[Chunk]:
        text = doc.text
        chunks: list[Chunk] = []
        start = 0
        stride = self._size - self._overlap
        while start < len(text):
            end = min(start + self._size, len(text))
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    Chunk(
                        text=piece,
                        source=doc.source,
                        chunk_id=str(uuid.uuid4()),
                        metadata=dict(doc.metadata),
                    )
                )
            start += stride
        return chunks

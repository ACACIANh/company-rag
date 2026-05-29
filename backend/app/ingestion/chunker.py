from shared.chunker import FixedSizeChunker
from shared.chunker.base import Chunker


def get_chunker(chunk_size: int = 500, chunk_overlap: int = 50) -> Chunker:
    return FixedSizeChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

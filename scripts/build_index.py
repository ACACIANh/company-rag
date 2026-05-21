"""docs/ 디렉터리를 청크로 분할하여 벡터 저장소에 인덱싱한다.

사용법:
    python -m scripts.build_index
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from shared.chunker import FixedSizeChunker
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.observability.cache import CachedEmbedder, LRUCache
from shared.vector_store.factory import create_vector_store


def build_index() -> None:
    config = load_config()
    embedder = CachedEmbedder(
        SentenceTransformerEmbedder(config.embedding_model),
        LRUCache(max_size=4096),
    )
    store = create_vector_store(config)
    indexer = Indexer(
        loader=MarkdownLoader(),
        chunker=FixedSizeChunker(chunk_size=500, chunk_overlap=50),
        embedder=embedder,
        store=store,
    )
    docs_path = os.path.join(_ROOT, "docs")
    count = indexer.index(docs_path)
    print(f"인덱싱 완료: {count}개 청크 ({docs_path})")


if __name__ == "__main__":
    build_index()

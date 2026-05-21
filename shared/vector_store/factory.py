from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore


def create_vector_store(config: Config) -> VectorStore:
    return ChromaStore(path=config.chroma_path, mode=config.chroma_mode)

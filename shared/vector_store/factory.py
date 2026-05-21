from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.chroma_store import ChromaStore


def create_vector_store(config: Config) -> VectorStore:
    if config.vector_store == "qdrant":
        from shared.vector_store.qdrant_store import QdrantStore
        return QdrantStore(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
            collection=config.qdrant_collection,
        )
    return ChromaStore(path=config.chroma_path, mode=config.chroma_mode)

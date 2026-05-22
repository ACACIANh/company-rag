from shared.config import load_config
from shared.indexer.indexer import Indexer
from shared.loader import MarkdownLoader
from shared.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


def build_index(docs_path: str) -> None:
    config = load_config()
    loader = MarkdownLoader()
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)
    store = create_vector_store(config)
    Indexer(loader=loader, chunker=chunker, embedder=embedder, store=store).index(docs_path)

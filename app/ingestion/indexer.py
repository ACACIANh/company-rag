from shared.config import load_config
from shared.fga.cache import make_cache_backend
from shared.fga.client import FGAClient
from shared.fga.models import FGAConfig
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

    fga_client = None
    if config.fga_store_id:
        fga_config = FGAConfig(
            api_url=config.fga_api_url,
            store_id=config.fga_store_id,
            api_key=config.fga_api_key,
            cache_ttl_seconds=config.fga_cache_ttl_seconds,
            pg_dsn=config.postgres_dsn,
        )
        fga_client = FGAClient(
            config=fga_config,
            cache=make_cache_backend(config.fga_cache_backend, config.postgres_dsn),
        )

    Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        fga_client=fga_client,
    ).index(docs_path)

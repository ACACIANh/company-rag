import os

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import load_config
from core.indexer.indexer import Indexer
from core.loader import MultiFormatLoader
from core.document_original.postgres_store import PostgresDocumentOriginalStore
from core.vector_store.factory import create_vector_store
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder


async def build_index(docs_path: str) -> None:
    config = load_config()
    # 코퍼스 루트 디렉토리명이 곧 최상위 폴더 path (docs/company → /company).
    base_path = "/" + os.path.basename(docs_path.rstrip("/"))
    loader = MultiFormatLoader(base_path=base_path)
    chunker = get_chunker()
    embedder = get_embedder(config.embedding_model)

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(config.postgres_dsn, init=_init_conn)
    store = create_vector_store(config, pool)
    original_store = PostgresDocumentOriginalStore(pool)
    await original_store.ensure_table()

    await Indexer(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        store=store,
        original_store=original_store,
    ).index(docs_path)

    await pool.close()

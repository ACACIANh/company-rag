import asyncpg

from core.config import Config
from core.vector_store.base import VectorStore
from core.vector_store.postgres_store import PostgresVectorStore


def create_vector_store(config: Config, pool: asyncpg.Pool) -> VectorStore:
    return PostgresVectorStore(pool)

import asyncpg

from shared.config import Config
from shared.vector_store.base import VectorStore
from shared.vector_store.postgres_store import PostgresVectorStore


def create_vector_store(config: Config, pool: asyncpg.Pool) -> VectorStore:
    return PostgresVectorStore(pool)

import asyncpg

from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore
from shared.session.adapters.postgres import PostgresSessionStore


def create_session_store(config: Config, pool: asyncpg.Pool | None = None) -> SessionStore:
    if config.session_store_type == "postgres" and pool is not None:
        return PostgresSessionStore(pool=pool)
    return InMemorySessionStore()

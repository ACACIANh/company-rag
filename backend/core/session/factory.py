import asyncpg

from core.config import Config
from core.session.base import SessionStore
from core.session.adapters.memory import InMemorySessionStore
from core.session.adapters.postgres import PostgresSessionStore


def create_session_store(config: Config, pool: asyncpg.Pool | None = None) -> SessionStore:
    if config.session_store_type == "postgres" and pool is not None:
        return PostgresSessionStore(pool=pool)
    return InMemorySessionStore()

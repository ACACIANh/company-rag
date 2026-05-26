from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore
from shared.session.adapters.postgres import PostgresSessionStore


def create_session_store(config: Config) -> SessionStore:
    if config.session_store_type == "postgres":
        return PostgresSessionStore(dsn=config.postgres_dsn)
    return InMemorySessionStore()

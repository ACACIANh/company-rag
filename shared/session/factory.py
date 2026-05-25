from shared.config import Config
from shared.session.base import SessionStore
from shared.session.adapters.memory import InMemorySessionStore


def create_session_store(config: Config) -> SessionStore:
    if config.session_store_type == "postgres":
        raise NotImplementedError(
            "PostgresSessionStore is not yet implemented. "
            "Set SESSION_STORE_TYPE=memory for development."
        )
    return InMemorySessionStore()

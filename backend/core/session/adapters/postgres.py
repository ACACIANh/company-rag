import dataclasses
import json

import asyncpg

from core.models import SourceRef
from core.session.base import SessionMeta, SessionStore, StoredMessage


def _to_source_ref(item) -> SourceRef:
    if isinstance(item, SourceRef):
        return item
    if isinstance(item, str):
        return SourceRef(source=item)
    return SourceRef(**item)


class PostgresSessionStore(SessionStore):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_tables(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    thread_id   TEXT        PRIMARY KEY,
                    user_id     TEXT        NOT NULL,
                    title       TEXT        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
                ON chat_sessions(user_id)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id          BIGSERIAL   PRIMARY KEY,
                    thread_id   TEXT        NOT NULL
                                    REFERENCES chat_sessions(thread_id) ON DELETE CASCADE,
                    role        TEXT        NOT NULL,
                    content     TEXT        NOT NULL,
                    sources     TEXT        NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
                ON chat_messages(thread_id, created_at)
            """)

    async def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chat_sessions (thread_id, user_id, title)
                VALUES ($1, $2, $3)
                ON CONFLICT (thread_id) DO NOTHING
            """, thread_id, user_id, title)

    async def list_sessions(self, user_id: str) -> list[SessionMeta]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT thread_id, title, created_at
                FROM chat_sessions
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            return [
                SessionMeta(
                    thread_id=row["thread_id"],
                    title=row["title"],
                    created_at=row["created_at"].isoformat(),
                )
                for row in rows
            ]

    async def get_messages(self, thread_id: str) -> list[StoredMessage]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, sources
                FROM chat_messages
                WHERE thread_id = $1
                ORDER BY created_at ASC
            """, thread_id)
            return [
                StoredMessage(
                    role=row["role"],
                    content=row["content"],
                    sources=[_to_source_ref(item) for item in json.loads(row["sources"])],
                )
                for row in rows
            ]

    async def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO chat_messages (thread_id, role, content, sources)
                    VALUES ($1, $2, $3, $4)
                """, thread_id, role, content,
                    json.dumps([dataclasses.asdict(s) for s in sources]))
            except asyncpg.ForeignKeyViolationError:
                pass

    async def delete_session(self, thread_id: str, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM chat_sessions
                WHERE thread_id = $1 AND user_id = $2
            """, thread_id, user_id)

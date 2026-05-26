import dataclasses
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from shared.models import SourceRef
from shared.session.base import SessionMeta, SessionStore, StoredMessage


def _to_source_ref(item) -> SourceRef:
    if isinstance(item, str):
        return SourceRef(source=item)
    return SourceRef(**item)


class PostgresSessionStore(SessionStore):
    def __init__(self, dsn: str, min_conn: int = 1, max_conn: int = 5) -> None:
        self._pool = pool.ThreadedConnectionPool(min_conn, max_conn, dsn)
        self._ensure_tables()

    @contextmanager
    def _conn(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _ensure_tables(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    thread_id   TEXT        PRIMARY KEY,
                    user_id     TEXT        NOT NULL,
                    title       TEXT        NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
                ON chat_sessions(user_id)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id          BIGSERIAL   PRIMARY KEY,
                    thread_id   TEXT        NOT NULL
                                    REFERENCES chat_sessions(thread_id) ON DELETE CASCADE,
                    role        TEXT        NOT NULL,
                    content     TEXT        NOT NULL,
                    sources     JSONB       NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
                ON chat_messages(thread_id, created_at)
            """)

    def create_session(self, thread_id: str, user_id: str, title: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_sessions (thread_id, user_id, title)
                VALUES (%s, %s, %s)
                ON CONFLICT (thread_id) DO NOTHING
            """, (thread_id, user_id, title))

    def list_sessions(self, user_id: str) -> list[SessionMeta]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT thread_id, title, created_at
                FROM chat_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            return [
                SessionMeta(
                    thread_id=row["thread_id"],
                    title=row["title"],
                    created_at=row["created_at"].isoformat(),
                )
                for row in cur.fetchall()
            ]

    def get_messages(self, thread_id: str) -> list[StoredMessage]:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT role, content, sources
                FROM chat_messages
                WHERE thread_id = %s
                ORDER BY created_at ASC
            """, (thread_id,))
            return [
                StoredMessage(
                    role=row["role"],
                    content=row["content"],
                    sources=[_to_source_ref(item) for item in row["sources"]],
                )
                for row in cur.fetchall()
            ]

    def add_message(
        self, thread_id: str, role: str, content: str, sources: list[SourceRef]
    ) -> None:
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_messages (thread_id, role, content, sources)
                    VALUES (%s, %s, %s, %s)
                """, (thread_id, role, content,
                      psycopg2.extras.Json([dataclasses.asdict(s) for s in sources])))
        except psycopg2.errors.ForeignKeyViolation:
            pass

    def delete_session(self, thread_id: str, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                DELETE FROM chat_sessions
                WHERE thread_id = %s AND user_id = %s
            """, (thread_id, user_id))

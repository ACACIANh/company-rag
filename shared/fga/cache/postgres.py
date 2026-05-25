import json
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class PostgresCacheBackend(PermissionCacheBackend):
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conn(self):
        return psycopg2.connect(self._dsn)

    def _ensure_table(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fga_permission_cache (
                    user_id       TEXT PRIMARY KEY,
                    teams         JSONB        NOT NULL DEFAULT '[]',
                    personal_docs JSONB        NOT NULL DEFAULT '[]',
                    expires_at    TIMESTAMPTZ  NOT NULL,
                    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_fga_cache_expires
                ON fga_permission_cache(expires_at)
            """)

    def get(self, user_id: str) -> UserPermission | None:
        with self._conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT teams, personal_docs FROM fga_permission_cache "
                "WHERE user_id = %s AND expires_at > now()",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return UserPermission(
                user_id=user_id,
                teams=row["teams"],
                personal_docs=row["personal_docs"],
            )

    def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO fga_permission_cache (user_id, teams, personal_docs, expires_at, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    teams = EXCLUDED.teams,
                    personal_docs = EXCLUDED.personal_docs,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
            """, (user_id, json.dumps(perm.teams), json.dumps(perm.personal_docs), expires_at))

    def invalidate(self, user_id: str) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fga_permission_cache WHERE user_id = %s", (user_id,))

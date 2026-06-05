import json
from datetime import datetime, timedelta, timezone

import asyncpg

from core.fga.base import PermissionCacheBackend


class PostgresCacheBackend(PermissionCacheBackend):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fga_permission_cache (
                    user_id     TEXT PRIMARY KEY,
                    folders     TEXT         NOT NULL DEFAULT '[]',
                    expires_at  TIMESTAMPTZ  NOT NULL,
                    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fga_cache_expires
                ON fga_permission_cache(expires_at)
            """)

    async def get(self, user_id: str) -> list[str] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT folders FROM fga_permission_cache "
                "WHERE user_id = $1 AND expires_at > now()",
                user_id,
            )
            if row is None:
                return None
            return json.loads(row["folders"])

    async def set(self, user_id: str, folders: list[str], ttl_seconds: int) -> None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=ttl_seconds)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO fga_permission_cache (user_id, folders, expires_at, updated_at)
                VALUES ($1, $2, $3, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    folders = EXCLUDED.folders,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = now()
            """, user_id, json.dumps(folders), expires_at)

    async def invalidate(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM fga_permission_cache WHERE user_id = $1", user_id
            )

    async def clear_all(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM fga_permission_cache")

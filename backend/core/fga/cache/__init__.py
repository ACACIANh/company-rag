import asyncpg

from core.fga.base import PermissionCacheBackend


def make_cache_backend(
    backend: str, pool: asyncpg.Pool | None = None
) -> PermissionCacheBackend:
    if backend == "postgres" and pool is not None:
        from core.fga.cache.postgres import PostgresCacheBackend
        return PostgresCacheBackend(pool)
    from core.fga.cache.memory import InMemoryCacheBackend
    return InMemoryCacheBackend()

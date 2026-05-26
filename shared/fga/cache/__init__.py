from shared.fga.base import PermissionCacheBackend


def make_cache_backend(backend: str, pg_dsn: str) -> PermissionCacheBackend:
    if backend == "postgres":
        from shared.fga.cache.postgres import PostgresCacheBackend
        return PostgresCacheBackend(pg_dsn)
    from shared.fga.cache.memory import InMemoryCacheBackend
    return InMemoryCacheBackend()

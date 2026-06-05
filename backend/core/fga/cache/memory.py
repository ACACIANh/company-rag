import time
from core.fga.base import PermissionCacheBackend


class InMemoryCacheBackend(PermissionCacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[list[str], float]] = {}

    async def get(self, user_id: str) -> list[str] | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        folders, expires_at = entry
        if time.time() > expires_at:
            del self._store[user_id]
            return None
        return folders

    async def set(self, user_id: str, folders: list[str], ttl_seconds: int) -> None:
        self._store[user_id] = (folders, time.time() + ttl_seconds)

    async def invalidate(self, user_id: str) -> None:
        self._store.pop(user_id, None)

    async def clear_all(self) -> None:
        self._store.clear()

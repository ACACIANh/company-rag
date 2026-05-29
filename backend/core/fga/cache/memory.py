import time
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import UserPermission


class InMemoryCacheBackend(PermissionCacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[UserPermission, float]] = {}

    async def get(self, user_id: str) -> UserPermission | None:
        entry = self._store.get(user_id)
        if entry is None:
            return None
        perm, expires_at = entry
        if time.time() > expires_at:
            del self._store[user_id]
            return None
        return perm

    async def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None:
        self._store[user_id] = (perm, time.time() + ttl_seconds)

    async def invalidate(self, user_id: str) -> None:
        self._store.pop(user_id, None)

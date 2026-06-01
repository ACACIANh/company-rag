from abc import ABC, abstractmethod


class PermissionCacheBackend(ABC):
    """user_id → 추려진 allowed_folders 캐시 (짧은 TTL)."""

    @abstractmethod
    async def get(self, user_id: str) -> list[str] | None: ...

    @abstractmethod
    async def set(self, user_id: str, folders: list[str], ttl_seconds: int) -> None: ...

    @abstractmethod
    async def invalidate(self, user_id: str) -> None: ...

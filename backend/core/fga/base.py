from abc import ABC, abstractmethod
from core.fga.models import UserPermission


class PermissionCacheBackend(ABC):
    @abstractmethod
    async def get(self, user_id: str) -> UserPermission | None: ...

    @abstractmethod
    async def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def invalidate(self, user_id: str) -> None: ...

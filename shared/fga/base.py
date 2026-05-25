from abc import ABC, abstractmethod
from shared.fga.models import UserPermission


class PermissionCacheBackend(ABC):
    @abstractmethod
    def get(self, user_id: str) -> UserPermission | None: ...

    @abstractmethod
    def set(self, user_id: str, perm: UserPermission, ttl_seconds: int) -> None: ...

    @abstractmethod
    def invalidate(self, user_id: str) -> None: ...

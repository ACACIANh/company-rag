from abc import ABC, abstractmethod


class PermissionCacheBackend(ABC):
    """user_id → 추려진 allowed_folders 캐시 (짧은 TTL)."""

    @abstractmethod
    async def get(self, user_id: str) -> list[str] | None: ...

    @abstractmethod
    async def set(self, user_id: str, folders: list[str], ttl_seconds: int) -> None: ...

    @abstractmethod
    async def invalidate(self, user_id: str) -> None: ...

    @abstractmethod
    async def clear_all(self) -> None:
        """캐시 전체 비우기 — 집합 권한 변경 시 멤버 무효화가 부분 실패하면 fail-closed 폴백으로 사용."""
        ...

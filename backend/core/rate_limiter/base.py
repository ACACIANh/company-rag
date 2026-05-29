from abc import ABC, abstractmethod


class RateLimiter(ABC):
    @abstractmethod
    def is_allowed(self, user_id: str, endpoint: str) -> bool: ...

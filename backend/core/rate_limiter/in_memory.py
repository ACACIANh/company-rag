import time
from collections import defaultdict, deque

from shared.rate_limiter.base import RateLimiter


class InMemoryRateLimiter(RateLimiter):
    def __init__(self, rules: dict[str, int], default_limit: int = 20) -> None:
        self._rules = rules
        self._default_limit = default_limit
        self._windows: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, user_id: str, endpoint: str) -> bool:
        limit = self._rules.get(endpoint, self._default_limit)
        key = f"{user_id}:{endpoint}"
        now = time.monotonic()
        window = self._windows[key]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

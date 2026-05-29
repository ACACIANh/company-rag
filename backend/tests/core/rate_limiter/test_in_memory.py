from core.rate_limiter.in_memory import InMemoryRateLimiter


def test_allows_under_limit():
    limiter = InMemoryRateLimiter(rules={"/chat": 3}, default_limit=3)
    for _ in range(3):
        assert limiter.is_allowed("user-1", "/chat") is True


def test_blocks_over_limit():
    limiter = InMemoryRateLimiter(rules={"/chat": 3}, default_limit=3)
    for _ in range(3):
        limiter.is_allowed("user-1", "/chat")
    assert limiter.is_allowed("user-1", "/chat") is False


def test_different_users_are_independent():
    limiter = InMemoryRateLimiter(rules={"/chat": 1}, default_limit=1)
    limiter.is_allowed("user-1", "/chat")
    assert limiter.is_allowed("user-2", "/chat") is True


def test_uses_default_limit_for_unknown_endpoint():
    limiter = InMemoryRateLimiter(rules={}, default_limit=2)
    limiter.is_allowed("user-1", "/other")
    limiter.is_allowed("user-1", "/other")
    assert limiter.is_allowed("user-1", "/other") is False

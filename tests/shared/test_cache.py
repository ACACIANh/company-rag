from shared.observability.cache import LRUCache


def test_lru_set_get():
    c = LRUCache(max_size=3)
    c.set("a", 1)
    assert c.get("a") == 1


def test_lru_miss_returns_none():
    c = LRUCache(max_size=3)
    assert c.get("missing") is None


def test_lru_eviction_oldest_first():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)  # evicts "a"
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_lru_get_promotes_recency():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    _ = c.get("a")   # "a" is now most-recent
    c.set("c", 3)    # evicts "b"
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_lru_overwrite():
    c = LRUCache(max_size=2)
    c.set("a", 1)
    c.set("a", 2)
    assert c.get("a") == 2

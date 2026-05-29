from unittest.mock import MagicMock

from shared.observability.cache import CachedEmbedder, LRUCache


def test_cached_embedder_calls_inner_on_miss():
    inner = MagicMock()
    inner.embed.return_value = [0.1, 0.2]
    ce = CachedEmbedder(inner=inner, cache=LRUCache(max_size=10))
    assert ce.embed("hello") == [0.1, 0.2]
    inner.embed.assert_called_once_with("hello")


def test_cached_embedder_skips_inner_on_hit():
    inner = MagicMock()
    inner.embed.return_value = [0.1, 0.2]
    ce = CachedEmbedder(inner=inner, cache=LRUCache(max_size=10))
    ce.embed("hello")
    ce.embed("hello")
    assert inner.embed.call_count == 1


def test_cached_embedder_batch_partial_hit():
    inner = MagicMock()
    inner.embed_batch.return_value = [[0.3, 0.4]]
    cache = LRUCache(max_size=10)
    ce = CachedEmbedder(inner=inner, cache=cache)
    # warm cache for "a"
    inner.embed.return_value = [0.1, 0.2]
    ce.embed("a")
    # batch with one hit + one miss
    inner.embed_batch.reset_mock()
    result = ce.embed_batch(["a", "b"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    # only the miss should be sent to inner
    inner.embed_batch.assert_called_once_with(["b"])

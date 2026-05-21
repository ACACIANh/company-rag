from unittest.mock import MagicMock

from shared.observability.cache import CachedLLM, LRUCache


def test_cached_llm_calls_inner_on_miss():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cl = CachedLLM(inner=inner, cache=LRUCache(max_size=10), model_name="m1")
    assert cl.complete("prompt") == "answer"
    inner.complete.assert_called_once_with("prompt")


def test_cached_llm_skips_inner_on_hit():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cl = CachedLLM(inner=inner, cache=LRUCache(max_size=10), model_name="m1")
    cl.complete("prompt")
    cl.complete("prompt")
    assert inner.complete.call_count == 1


def test_cached_llm_different_model_different_key():
    inner = MagicMock()
    inner.complete.return_value = "answer"
    cache = LRUCache(max_size=10)
    cl_a = CachedLLM(inner=inner, cache=cache, model_name="m-a")
    cl_b = CachedLLM(inner=inner, cache=cache, model_name="m-b")
    cl_a.complete("p")
    cl_b.complete("p")
    assert inner.complete.call_count == 2

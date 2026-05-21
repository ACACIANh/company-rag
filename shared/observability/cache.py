import hashlib
from collections import OrderedDict
from typing import Any

from shared.embedder.base import Embedder
from shared.llm.base import LLMClient


class LRUCache:
    def __init__(self, max_size: int = 1024) -> None:
        self._max = max_size
        self._data: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)


class CachedEmbedder(Embedder):
    """Caching decorator that wraps a concrete Embedder."""

    def __init__(self, inner: Embedder, cache: LRUCache) -> None:
        self._inner = inner
        self._cache = cache

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> list[float]:
        k = self._key(text)
        cached = self._cache.get(k)
        if cached is not None:
            return cached
        v = self._inner.embed(text)
        self._cache.set(k, v)
        return v

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        for i, t in enumerate(texts):
            cached = self._cache.get(self._key(t))
            if cached is not None:
                results[i] = cached
            else:
                missing_indices.append(i)
                missing_texts.append(t)
        if missing_texts:
            fresh = self._inner.embed_batch(missing_texts)
            for idx, vec, txt in zip(missing_indices, fresh, missing_texts):
                results[idx] = vec
                self._cache.set(self._key(txt), vec)
        return results  # type: ignore[return-value]


class CachedLLM(LLMClient):
    def __init__(self, inner: LLMClient, cache: LRUCache, model_name: str = "") -> None:
        self._inner = inner
        self._cache = cache
        self._model = model_name

    def _key(self, prompt: str) -> str:
        return hashlib.sha256((self._model + "::" + prompt).encode("utf-8")).hexdigest()

    def complete(self, prompt: str) -> str:
        k = self._key(prompt)
        cached = self._cache.get(k)
        if cached is not None:
            return cached
        v = self._inner.complete(prompt)
        self._cache.set(k, v)
        return v

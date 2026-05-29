import os

from openai import OpenAI

from core.embedder.base import Embedder


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._model = model_name
        self._client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY", ""),
            timeout=timeout,
            max_retries=max_retries,
        )

    def embed(self, text: str) -> list[float]:
        return self._client.embeddings.create(input=text, model=self._model).data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in resp.data]

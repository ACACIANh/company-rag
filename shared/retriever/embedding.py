from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()

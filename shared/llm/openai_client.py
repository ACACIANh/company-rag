from collections.abc import AsyncIterator

from openai import OpenAI

from shared.llm.base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        raise NotImplementedError  # Task 2에서 구현 예정
        yield  # AsyncIterator[str] 타입을 위한 async generator 선언

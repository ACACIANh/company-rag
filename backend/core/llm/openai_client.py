from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from core.llm.base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
        self._async_client = AsyncOpenAI(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        response = await self._async_client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content

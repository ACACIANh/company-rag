from collections.abc import AsyncIterator

import anthropic

from core.llm.base import LLMClient


class AnthropicClient(LLMClient):
    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self._async_client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self._model = model

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with self._async_client.messages.stream(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            async for text in s.text_stream:
                yield text

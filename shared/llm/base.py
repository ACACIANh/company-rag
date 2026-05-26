from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str: ...

    @abstractmethod
    def stream(self, prompt: str) -> AsyncIterator[str]: ...

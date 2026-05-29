from typing import Any
from langchain_core.language_models import BaseLLM
from langchain_core.outputs import Generation, LLMResult
from pydantic import Field


class LangChainLLMAdapter(BaseLLM):
    """core.LLMClient를 LangChain BaseLLM(Runnable)으로 래핑하는 어댑터."""

    llm_client: Any = Field(...)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "shared_llm_adapter"

    def _generate(self, prompts: list[str], **kwargs: Any) -> LLMResult:
        return LLMResult(
            generations=[
                [Generation(text=self.llm_client.complete(p))] for p in prompts
            ]
        )

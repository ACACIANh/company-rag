from shared.config import Config
from shared.llm.base import LLMClient
from shared.llm.anthropic_client import AnthropicClient
from shared.llm.openai_client import OpenAIClient


def create_llm(config: Config) -> LLMClient:
    if config.llm_provider == "anthropic":
        return AnthropicClient(
            model=config.llm_model, api_key=config.anthropic_api_key
        )
    return OpenAIClient(model=config.llm_model, api_key=config.openai_api_key)

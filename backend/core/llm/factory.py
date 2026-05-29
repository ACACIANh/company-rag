from core.config import Config
from core.llm.base import LLMClient
from core.llm.anthropic_client import AnthropicClient
from core.llm.openai_client import OpenAIClient


def create_llm(config: Config) -> LLMClient:
    if config.llm_provider == "anthropic":
        return AnthropicClient(
            model=config.llm_model, api_key=config.anthropic_api_key
        )
    return OpenAIClient(model=config.llm_model, api_key=config.openai_api_key)


def create_chat_llm(config: Config):
    """bind_tools를 지원하는 LangChain BaseChatModel 반환."""
    if config.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config.llm_model, api_key=config.anthropic_api_key)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=config.llm_model, api_key=config.openai_api_key)

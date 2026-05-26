import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from shared.config import Config
from shared.llm.base import LLMClient
from shared.llm.openai_client import OpenAIClient
from shared.llm.anthropic_client import AnthropicClient
from shared.llm.factory import create_llm


def test_llm_client_is_abstract():
    with pytest.raises(TypeError):
        LLMClient()


def test_openai_client_complete(mocker):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "테스트 답변"
    mocker.patch("shared.llm.openai_client.OpenAI")

    client = OpenAIClient(model="gpt-4o-mini", api_key="test-key")
    client._client.chat.completions.create.return_value = mock_response

    result = client.complete("테스트 질문")

    assert result == "테스트 답변"


def test_anthropic_client_complete(mocker):
    mock_response = MagicMock()
    mock_response.content[0].text = "테스트 답변"
    mocker.patch("shared.llm.anthropic_client.anthropic.Anthropic")

    client = AnthropicClient(model="claude-3-haiku-20240307", api_key="test-key")
    client._client.messages.create.return_value = mock_response

    result = client.complete("테스트 질문")

    assert result == "테스트 답변"


def test_factory_creates_openai_by_default(mocker):
    mocker.patch("shared.llm.openai_client.OpenAI")
    config = Config(
        llm_provider="openai", llm_model="gpt-4o-mini",
        openai_api_key="sk-test", anthropic_api_key="",
        embedding_model="test-model",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
        cors_origins=["http://localhost:5173"],
        reranker_type="none",
        reranker_base_url="",
        reranker_model="",
        reranker_api_key="",
        session_store_type="memory",
        postgres_dsn="",
        fga_api_url="http://localhost:8080",
        fga_store_id="",
        fga_api_key="",
        fga_cache_backend="memory",
        fga_cache_ttl_seconds=60,
    )
    llm = create_llm(config)
    assert isinstance(llm, OpenAIClient)


def test_factory_creates_anthropic(mocker):
    mocker.patch("shared.llm.anthropic_client.anthropic.Anthropic")
    config = Config(
        llm_provider="anthropic", llm_model="claude-3-haiku-20240307",
        openai_api_key="", anthropic_api_key="sk-ant-test",
        embedding_model="test-model",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
        cors_origins=["http://localhost:5173"],
        reranker_type="none",
        reranker_base_url="",
        reranker_model="",
        reranker_api_key="",
        session_store_type="memory",
        postgres_dsn="",
        fga_api_url="http://localhost:8080",
        fga_store_id="",
        fga_api_key="",
        fga_cache_backend="memory",
        fga_cache_ttl_seconds=60,
    )
    llm = create_llm(config)
    assert isinstance(llm, AnthropicClient)


def test_llm_abstract_requires_stream():
    """stream()을 구현하지 않은 서브클래스는 인스턴스화 불가."""
    class NoStream(LLMClient):
        def complete(self, prompt: str) -> str:
            return ""
    with pytest.raises(TypeError):
        NoStream()


async def test_anthropic_client_stream(mocker):
    """stream()이 토큰 시퀀스를 yield한다."""
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    async def _text_stream():
        for t in ["안", "녕", "하", "세요"]:
            yield t

    mock_stream_ctx.text_stream = _text_stream()
    mocker.patch("shared.llm.anthropic_client.anthropic.AsyncAnthropic")

    client = AnthropicClient(model="claude-3-haiku-20240307", api_key="test-key")
    client._async_client.messages.stream.return_value = mock_stream_ctx

    tokens = []
    async for token in client.stream("테스트"):
        tokens.append(token)

    assert tokens == ["안", "녕", "하", "세요"]

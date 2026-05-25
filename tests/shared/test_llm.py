import pytest
from unittest.mock import MagicMock, patch
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


def test_factory_creates_openai_by_default(monkeypatch, mocker):
    mocker.patch("shared.llm.openai_client.OpenAI")
    config = Config(
        llm_provider="openai", llm_model="gpt-4o-mini",
        openai_api_key="sk-test", anthropic_api_key="",
        vector_store="chroma", chroma_mode="embedded",
        chroma_path=".chroma", embedding_model="test-model",
        qdrant_url="", qdrant_api_key="", qdrant_collection="documents",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
        cors_origins=["http://localhost:5173"],
        reranker_type="none",
        reranker_base_url="",
        reranker_model="",
        reranker_api_key="",
    )
    llm = create_llm(config)
    assert isinstance(llm, OpenAIClient)


def test_factory_creates_anthropic(mocker):
    mocker.patch("shared.llm.anthropic_client.anthropic.Anthropic")
    config = Config(
        llm_provider="anthropic", llm_model="claude-3-haiku-20240307",
        openai_api_key="", anthropic_api_key="sk-ant-test",
        vector_store="chroma", chroma_mode="embedded",
        chroma_path=".chroma", embedding_model="test-model",
        qdrant_url="", qdrant_api_key="", qdrant_collection="documents",
        jwt_secret="test-secret",
        jwt_expire_minutes=60,
        rate_limit_per_minute=20,
        cors_origins=["http://localhost:5173"],
        reranker_type="none",
        reranker_base_url="",
        reranker_model="",
        reranker_api_key="",
    )
    llm = create_llm(config)
    assert isinstance(llm, AnthropicClient)

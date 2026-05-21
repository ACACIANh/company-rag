import os
import pytest
from shared.config import Config, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.delenv("CHROMA_MODE", raising=False)
    monkeypatch.delenv("CHROMA_PATH", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    config = load_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert config.vector_store == "chroma"
    assert config.chroma_mode == "embedded"
    assert config.chroma_path == "./.chroma"


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-haiku-20240307")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    config = load_config()

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-3-haiku-20240307"
    assert config.anthropic_api_key == "sk-ant-test"


def test_load_config_qdrant_defaults(monkeypatch):
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)

    config = load_config()

    assert config.qdrant_url == ""
    assert config.qdrant_api_key == ""
    assert config.qdrant_collection == "documents"


def test_load_config_qdrant_from_env(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://xyz.qdrant.io:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-api-key")
    monkeypatch.setenv("QDRANT_COLLECTION", "my-collection")

    config = load_config()

    assert config.qdrant_url == "https://xyz.qdrant.io:6333"
    assert config.qdrant_api_key == "test-api-key"
    assert config.qdrant_collection == "my-collection"

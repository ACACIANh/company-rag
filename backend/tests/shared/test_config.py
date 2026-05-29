from shared.config import load_config


def test_load_config_defaults(monkeypatch):
    for key in ["LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "EMBEDDING_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    config = load_config()

    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4o-mini"
    assert not hasattr(config, "chroma_mode")
    assert not hasattr(config, "chroma_path")
    assert not hasattr(config, "vector_store")


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-haiku-20240307")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    config = load_config()

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-3-haiku-20240307"
    assert config.anthropic_api_key == "sk-ant-test"


def test_cors_origins_defaults_to_localhost_vite(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    config = load_config()
    assert config.cors_origins == ["http://localhost:5173"]


def test_cors_origins_parsed_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    config = load_config()
    assert config.cors_origins == ["https://a.example", "https://b.example"]


def test_config_fga_defaults(monkeypatch):
    for key in ["FGA_API_URL", "FGA_STORE_ID", "FGA_API_KEY",
                "FGA_CACHE_BACKEND", "FGA_CACHE_TTL_SECONDS"]:
        monkeypatch.delenv(key, raising=False)
    config = load_config()
    assert config.fga_api_url == "http://localhost:8080"
    assert config.fga_store_id == ""
    assert config.fga_api_key == ""
    assert config.fga_cache_backend == "memory"
    assert config.fga_cache_ttl_seconds == 60

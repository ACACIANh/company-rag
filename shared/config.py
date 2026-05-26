import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS")
    if not raw:
        return ["http://localhost:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass
class Config:
    llm_provider: str
    llm_model: str
    openai_api_key: str
    anthropic_api_key: str
    vector_store: str
    chroma_mode: str
    chroma_path: str
    embedding_model: str
    jwt_secret: str
    jwt_expire_minutes: int
    rate_limit_per_minute: int
    cors_origins: list[str]
    reranker_type: str        # "none" | "llm" | "rrf"
    reranker_base_url: str    # 사내 LLM URL; "" = OpenAI 기본값
    reranker_model: str
    reranker_api_key: str     # "" → openai_api_key fallback
    session_store_type: str   # "memory" | "postgres"
    postgres_dsn: str         # prod: postgresql://user:pass@host/db
    fga_api_url: str
    fga_store_id: str
    fga_api_key: str
    fga_cache_backend: str    # "postgres" | "memory"
    fga_cache_ttl_seconds: int


def load_config() -> Config:
    return Config(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        vector_store=os.getenv("VECTOR_STORE", "chroma"),
        chroma_mode=os.getenv("CHROMA_MODE", "embedded"),
        chroma_path=os.getenv("CHROMA_PATH", "./.chroma"),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        ),
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-prod"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
        cors_origins=_parse_cors_origins(),
        reranker_type=os.getenv("RERANKER_TYPE", "none"),
        reranker_base_url=os.getenv("RERANKER_BASE_URL", ""),
        reranker_model=os.getenv("RERANKER_MODEL", "gpt-4o-mini"),
        reranker_api_key=os.getenv("RERANKER_API_KEY", ""),
        session_store_type=os.getenv("SESSION_STORE_TYPE", "memory"),
        postgres_dsn=os.getenv("POSTGRES_DSN", ""),
        fga_api_url=os.getenv("FGA_API_URL", "http://localhost:8080"),
        fga_store_id=os.getenv("FGA_STORE_ID", ""),
        fga_api_key=os.getenv("FGA_API_KEY", ""),
        fga_cache_backend=os.getenv("FGA_CACHE_BACKEND", "memory"),
        fga_cache_ttl_seconds=int(os.getenv("FGA_CACHE_TTL_SECONDS", "60")),
    )

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str
    jwt_secret: str
    jwt_expire_minutes: int
    rate_limit_per_minute: int


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
        qdrant_url=os.getenv("QDRANT_URL", ""),
        qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "documents"),
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret-change-in-prod"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
    )

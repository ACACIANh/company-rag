from dataclasses import dataclass, field


@dataclass
class UserPermission:
    user_id: str
    teams: list[str] = field(default_factory=list)
    personal_docs: list[str] = field(default_factory=list)


@dataclass
class FGAConfig:
    api_url: str
    store_id: str
    api_key: str = ""
    cache_ttl_seconds: int = 60
    pg_dsn: str = ""   # 설정 시 personal_docs를 user_doc_grants 테이블에서 조회

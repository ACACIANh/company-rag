from dataclasses import dataclass


@dataclass
class FGAConfig:
    api_url: str
    store_id: str
    api_key: str = ""
    cache_ttl_seconds: int = 60

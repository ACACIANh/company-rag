from dataclasses import dataclass, field

from shared.models import SearchResult


@dataclass
class Context:
    query: str
    chunks: list[SearchResult] = field(default_factory=list)
    answer_text: str | None = None
    metadata: dict = field(default_factory=dict)

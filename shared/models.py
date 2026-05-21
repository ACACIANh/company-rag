from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: str


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


@dataclass
class Answer:
    text: str
    sources: list[str]
    trace: list[dict] | None = None

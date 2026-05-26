from dataclasses import dataclass, field


@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    text: str
    source: str
    chunk_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


@dataclass
class SourceRef:
    source: str
    document_id: str = ""
    sensitivity: str = "public"
    team_id: str = ""


@dataclass
class Answer:
    text: str
    sources: list[SourceRef]
    trace: list[dict] | None = None

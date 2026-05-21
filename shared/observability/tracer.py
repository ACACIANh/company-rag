import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float = 0.0
    metadata: dict = field(default_factory=dict)


class Tracer:
    def __init__(self) -> None:
        self.spans: list[Span] = []

    @contextmanager
    def span(self, name: str):
        s = Span(name=name, started_at=time.time())
        self.spans.append(s)
        try:
            yield s
        finally:
            s.ended_at = time.time()

    def dump(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "metadata": dict(s.metadata),
            }
            for s in self.spans
        ]

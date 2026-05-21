from shared.observability.tracer import Span


def recall_at_k(retrieved_sources: list[str], expected_source: str, k: int) -> float:
    return 1.0 if expected_source in retrieved_sources[:k] else 0.0


def latency_ms(span: Span) -> float:
    return (span.ended_at - span.started_at) * 1000.0

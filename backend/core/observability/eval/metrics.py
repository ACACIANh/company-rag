from core.observability.tracer import Span


def recall_at_k(retrieved_sources: list[str], expected_source: str, k: int) -> float:
    return 1.0 if expected_source in retrieved_sources[:k] else 0.0


def mrr(retrieved_sources: list[str], expected_source: str) -> float:
    if not expected_source:
        return 0.0
    try:
        rank = retrieved_sources.index(expected_source) + 1
        return 1.0 / rank
    except ValueError:
        return 0.0


def keyword_hit_rate(answer_text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    hits = sum(1 for kw in expected_keywords if kw in answer_text)
    return hits / len(expected_keywords)


def latency_ms(span: Span) -> float:
    return (span.ended_at - span.started_at) * 1000.0

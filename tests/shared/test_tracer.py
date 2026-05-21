import pytest

from shared.observability.tracer import Tracer, Span


def test_tracer_records_single_span():
    tracer = Tracer()
    with tracer.span("step1") as s:
        s.metadata["k"] = "v"
    assert len(tracer.spans) == 1
    span = tracer.spans[0]
    assert span.name == "step1"
    assert span.metadata == {"k": "v"}
    assert span.ended_at >= span.started_at


def test_tracer_records_multiple_spans_in_order():
    tracer = Tracer()
    with tracer.span("a"):
        pass
    with tracer.span("b"):
        pass
    assert [s.name for s in tracer.spans] == ["a", "b"]


def test_tracer_records_span_on_exception():
    tracer = Tracer()
    with pytest.raises(ValueError):
        with tracer.span("explode") as s:
            s.metadata["status"] = "error"
            raise ValueError("boom")
    assert len(tracer.spans) == 1
    assert tracer.spans[0].metadata.get("status") == "error"


def test_tracer_dump_returns_list_of_dicts():
    tracer = Tracer()
    with tracer.span("step1") as s:
        s.metadata["latency_ms"] = 42
    dumped = tracer.dump()
    assert isinstance(dumped, list)
    assert isinstance(dumped[0], dict)
    assert dumped[0]["name"] == "step1"
    assert "started_at" in dumped[0]
    assert "ended_at" in dumped[0]
    assert dumped[0]["metadata"] == {"latency_ms": 42}

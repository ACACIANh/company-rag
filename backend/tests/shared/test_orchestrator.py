import pytest

from shared.observability.tracer import Tracer
from shared.orchestrator import Context, Pipeline, Step


class _SetAnswer(Step):
    name = "set_answer"

    def __init__(self, value: str) -> None:
        self._value = value

    def run(self, ctx: Context) -> Context:
        ctx.answer_text = self._value
        return ctx


class _AppendMeta(Step):
    name = "append_meta"

    def run(self, ctx: Context) -> Context:
        ctx.metadata.setdefault("visited", []).append(self.name)
        return ctx


class _Boom(Step):
    name = "boom"

    def run(self, ctx: Context) -> Context:
        raise RuntimeError("kaboom")


def test_context_defaults():
    ctx = Context(query="q")
    assert ctx.query == "q"
    assert ctx.chunks == []
    assert ctx.answer_text is None
    assert ctx.metadata == {}


def test_pipeline_runs_steps_in_order():
    p = Pipeline(steps=[_AppendMeta(), _SetAnswer("hello")])
    ctx = p.run(Context(query="q"))
    assert ctx.metadata["visited"] == ["append_meta"]
    assert ctx.answer_text == "hello"


def test_pipeline_with_tracer_records_span_per_step():
    tracer = Tracer()
    p = Pipeline(steps=[_AppendMeta(), _SetAnswer("ok")], tracer=tracer)
    p.run(Context(query="q"))
    assert [s.name for s in tracer.spans] == ["append_meta", "set_answer"]


def test_pipeline_records_error_in_span_and_reraises():
    tracer = Tracer()
    p = Pipeline(steps=[_Boom()], tracer=tracer)
    with pytest.raises(RuntimeError):
        p.run(Context(query="q"))
    assert tracer.spans[0].metadata.get("status") == "error"
    assert tracer.spans[0].metadata.get("error") == "RuntimeError"

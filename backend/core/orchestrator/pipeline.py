from shared.observability.tracer import Tracer
from shared.orchestrator.context import Context
from shared.orchestrator.step import Step


class Pipeline:
    def __init__(self, steps: list[Step], tracer: Tracer | None = None) -> None:
        self._steps = steps
        self._tracer = tracer

    def run(self, ctx: Context) -> Context:
        for step in self._steps:
            if self._tracer is not None:
                with self._tracer.span(step.name) as span:
                    try:
                        ctx = step.run(ctx)
                    except Exception as e:
                        span.metadata["status"] = "error"
                        span.metadata["error"] = type(e).__name__
                        raise
            else:
                ctx = step.run(ctx)
        return ctx

from shared.observability.sinks.base import CostSink

_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
}

_tracker: "CostTracker | None" = None


class CostTracker:
    def __init__(self, sinks: list[CostSink]) -> None:
        self._sinks = sinks

    def track(
        self, user_id: str, input_tokens: int, output_tokens: int, model: str
    ) -> None:
        pricing = _MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
        for sink in self._sinks:
            sink.record(user_id, input_tokens, output_tokens, cost, model)


def init_tracker(sinks: list[CostSink]) -> None:
    global _tracker
    _tracker = CostTracker(sinks)


def get_tracker() -> "CostTracker | None":
    return _tracker

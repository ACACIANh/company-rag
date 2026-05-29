from unittest.mock import MagicMock
from core.observability.cost_tracker import CostTracker
from core.observability.sinks.base import CostSink


def _make_sink() -> CostSink:
    return MagicMock(spec=CostSink)


def test_track_calls_all_sinks():
    sink1, sink2 = _make_sink(), _make_sink()
    tracker = CostTracker(sinks=[sink1, sink2])
    tracker.track("user-1", input_tokens=100, output_tokens=50, model="gpt-4o-mini")
    sink1.record.assert_called_once()
    sink2.record.assert_called_once()


def test_track_calculates_cost_for_gpt4o_mini():
    sink = _make_sink()
    tracker = CostTracker(sinks=[sink])
    tracker.track("user-1", input_tokens=1_000_000, output_tokens=0, model="gpt-4o-mini")
    # gpt-4o-mini input: $0.15 per 1M tokens
    call_args = sink.record.call_args
    cost_arg = call_args[0][3] if call_args[0] else call_args[1]["cost_usd"]
    assert abs(cost_arg - 0.15) < 0.001


def test_track_with_no_sinks_does_not_raise():
    tracker = CostTracker(sinks=[])
    tracker.track("user-1", input_tokens=100, output_tokens=50, model="gpt-4o-mini")

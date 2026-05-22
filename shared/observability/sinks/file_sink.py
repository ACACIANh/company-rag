import json
from datetime import datetime, timezone
from pathlib import Path

from shared.observability.sinks.base import CostSink


class FileSink(CostSink):
    def __init__(self, log_dir: str = "logs") -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(exist_ok=True)

    def record(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str,
    ) -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._dir / f"cost_{date}.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
            "model": model,
        }
        with path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

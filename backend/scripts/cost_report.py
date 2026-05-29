"""일일 비용 리포트 — logs/cost_*.jsonl 파일을 읽어 날짜/모델/유저별로 집계한다.

Usage:
    python scripts/cost_report.py          # 전체 기간
    python scripts/cost_report.py --date 2026-05-25   # 특정 날짜
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_entries(log_dir: Path, date_filter: str | None) -> list[dict]:
    pattern = f"cost_{date_filter}.jsonl" if date_filter else "cost_*.jsonl"
    entries = []
    for path in sorted(log_dir.glob(pattern)):
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def report(entries: list[dict]) -> None:
    if not entries:
        print("집계할 로그가 없습니다.")
        return

    by_date: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "calls": 0})
    by_model: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "calls": 0})
    by_user: dict[str, float] = defaultdict(float)

    for e in entries:
        date = e["ts"][:10]
        by_date[date]["cost"] += e["cost_usd"]
        by_date[date]["input"] += e["input_tokens"]
        by_date[date]["output"] += e["output_tokens"]
        by_date[date]["calls"] += 1
        by_model[e["model"]]["cost"] += e["cost_usd"]
        by_model[e["model"]]["calls"] += 1
        by_user[e["user_id"]] += e["cost_usd"]

    total = sum(v["cost"] for v in by_date.values())

    print("=" * 50)
    print("  LLM 비용 리포트")
    print("=" * 50)

    print("\n[날짜별]")
    for date, v in sorted(by_date.items()):
        print(f"  {date}  ${v['cost']:.6f}  ({v['calls']}건, in={v['input']} out={v['output']})")

    print("\n[모델별]")
    for model, v in sorted(by_model.items(), key=lambda x: -x[1]["cost"]):
        print(f"  {model:<25} ${v['cost']:.6f}  ({v['calls']}건)")

    print("\n[유저별]")
    for user, cost in sorted(by_user.items(), key=lambda x: -x[1]):
        print(f"  {user:<20} ${cost:.6f}")

    print("\n" + "-" * 50)
    print(f"  합계: ${total:.6f}  총 {len(entries)}건")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD 형식으로 특정 날짜만 집계")
    parser.add_argument("--log-dir", default="logs", help="로그 디렉터리 경로 (기본: logs)")
    args = parser.parse_args()

    entries = load_entries(Path(args.log_dir), args.date)
    report(entries)

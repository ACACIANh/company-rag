import os
from typing import Callable

import yaml

from shared.observability.eval.evaluator import EvalCase, Evaluator


def load_questions(yaml_path: str | None = None) -> list[dict]:
    path = yaml_path or os.path.join(os.path.dirname(__file__), "questions.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def run_eval(run: Callable, yaml_path: str | None = None) -> None:
    """주어진 run(question) 함수를 questions.yaml 전체에 대해 채점."""
    raw = load_questions(yaml_path)
    cases = [
        EvalCase(
            question=q["question"],
            expected_keywords=q.get("expected_keywords", []),
            expected_source=q.get("expected_source", ""),
        )
        for q in raw
    ]
    report = Evaluator(k=5).evaluate(run, cases)

    print("\n=== EVAL REPORT ===")
    for c in report.cases:
        line = f"Q: {c['question']:<40}"
        if "error" in c:
            line += f"  ERROR: {c['error']}"
        else:
            line += (
                f"  recall@5={c['recall_at_k']:.2f}"
                f"  keyword_hit={c['keyword_hit_rate']:.2f}"
                f"  src={c.get('sources')}"
            )
        print(line)
    print(f"\nAggregate: {report.aggregate}")

import os
from typing import Callable

import yaml

from shared.observability.eval.evaluator import EvalCase, Evaluator

_EVAL_KS = [1, 3, 5]


def load_questions(yaml_path: str | None = None) -> list[dict]:
    path = yaml_path or os.path.join(os.path.dirname(__file__), "questions.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def run_eval(run: Callable, yaml_path: str | None = None, label: str = "") -> None:
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
    report = Evaluator(k=5, eval_ks=_EVAL_KS).evaluate(run, cases)

    header = f"=== EVAL REPORT{f' [{label}]' if label else ''} ==="
    print(f"\n{header}")
    for c in report.cases:
        line = f"Q: {c['question']:<42}"
        if "error" in c:
            line += f"  ERROR: {c['error']}"
        else:
            recalls = "  ".join(
                f"recall@{k}={c.get(f'recall_at_{k}', 0):.2f}" for k in _EVAL_KS
            )
            line += f"  {recalls}  mrr={c.get('mrr', 0):.2f}  kw={c['keyword_hit_rate']:.2f}"
        print(line)

    agg = report.aggregate
    recall_summary = "  ".join(
        f"recall@{k}={agg.get(f'mean_recall_at_{k}', 0):.3f}" for k in _EVAL_KS
    )
    print(f"\nAggregate: {recall_summary}  mrr={agg['mean_mrr']:.3f}  kw={agg['mean_keyword_hit_rate']:.3f}  errors={agg['n_errors']}/{agg['n_cases']}")

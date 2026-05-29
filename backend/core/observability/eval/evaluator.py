from dataclasses import dataclass, field
from typing import Callable

from core.models import Answer
from core.observability.eval.metrics import keyword_hit_rate, mrr, recall_at_k

_DEFAULT_EVAL_KS = [1, 3, 5]


@dataclass
class EvalCase:
    question: str
    expected_keywords: list[str]
    expected_source: str


@dataclass
class EvalReport:
    cases: list[dict] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)


class Evaluator:
    def __init__(self, k: int = 5, eval_ks: list[int] | None = None) -> None:
        self._k = k
        self._eval_ks = sorted(set(eval_ks or _DEFAULT_EVAL_KS))

    def evaluate(
        self, workflow: Callable[[str], Answer], cases: list[EvalCase]
    ) -> EvalReport:
        results: list[dict] = []
        for case in cases:
            entry: dict = {
                "question": case.question,
                "expected_source": case.expected_source,
            }
            try:
                ans = workflow(case.question)
                entry["answer"] = ans.text
                entry["sources"] = ans.sources
                entry["recall_at_k"] = recall_at_k(ans.sources, case.expected_source, self._k)
                entry["mrr"] = mrr(ans.sources, case.expected_source)
                for k in self._eval_ks:
                    entry[f"recall_at_{k}"] = recall_at_k(ans.sources, case.expected_source, k)
                entry["keyword_hit_rate"] = keyword_hit_rate(ans.text, case.expected_keywords)
            except Exception as e:
                entry["error"] = type(e).__name__
            results.append(entry)

        recalls = [r["recall_at_k"] for r in results if "recall_at_k" in r]
        hits = [r["keyword_hit_rate"] for r in results if "keyword_hit_rate" in r]
        mrrs = [r["mrr"] for r in results if "mrr" in r]
        agg: dict = {
            "mean_recall_at_k": sum(recalls) / len(recalls) if recalls else 0.0,
            "mean_mrr": sum(mrrs) / len(mrrs) if mrrs else 0.0,
            "mean_keyword_hit_rate": sum(hits) / len(hits) if hits else 0.0,
            "n_cases": len(cases),
            "n_errors": sum(1 for r in results if "error" in r),
        }
        for k in self._eval_ks:
            vals = [r[f"recall_at_{k}"] for r in results if f"recall_at_{k}" in r]
            agg[f"mean_recall_at_{k}"] = sum(vals) / len(vals) if vals else 0.0
        return EvalReport(cases=results, aggregate=agg)

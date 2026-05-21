from dataclasses import dataclass, field
from typing import Callable

from shared.models import Answer
from shared.observability.eval.metrics import keyword_hit_rate, recall_at_k


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
    def __init__(self, k: int = 5) -> None:
        self._k = k

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
                entry["keyword_hit_rate"] = keyword_hit_rate(ans.text, case.expected_keywords)
            except Exception as e:
                entry["error"] = type(e).__name__
            results.append(entry)

        recalls = [r["recall_at_k"] for r in results if "recall_at_k" in r]
        hits = [r["keyword_hit_rate"] for r in results if "keyword_hit_rate" in r]
        agg = {
            "mean_recall_at_k": sum(recalls) / len(recalls) if recalls else 0.0,
            "mean_keyword_hit_rate": sum(hits) / len(hits) if hits else 0.0,
            "n_cases": len(cases),
            "n_errors": sum(1 for r in results if "error" in r),
        }
        return EvalReport(cases=results, aggregate=agg)

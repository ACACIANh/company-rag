import os
from typing import Callable

import yaml

from core.observability.eval.evaluator import EvalCase, Evaluator
from tests.eval.route_metrics import (
    RouteEvalReport,
    format_route_report,
    score_routes,
)

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


def run_route_eval(
    predict_route: Callable[[str], str],
    yaml_path: str | None = None,
    label: str = "",
) -> RouteEvalReport:
    """expected_route 라벨에 대해 라우팅 정확도를 채점 (ADR-0022 Decision 3).

    predict_route(question) -> str 를 주입식으로 받아 LLM 없이 테스트 가능하다.
    questions.yaml 의 expected_route 를 정규화(tool_call→agent)해 predicted 와 비교한다.
    """
    raw = load_questions(yaml_path)
    pairs: list[tuple[str, str]] = []
    for q in raw:
        expected = q.get("expected_route")
        if not expected:
            continue
        predicted = predict_route(q["question"])
        pairs.append((predicted, expected))

    report = score_routes(pairs)
    print(f"\n{format_route_report(report, label=label)}")
    return report


def _live_predict_route() -> Callable[[str], str]:
    """실제 LLM 으로 router_node 를 돌리는 thin 라이브 래퍼.

    compare_reranker.main() 의 라이브 구성 선례를 따른다. router_node 는 순수 함수라
    전체 그래프를 빌드하지 않고 최소 state + 실 LLM 으로 route 만 뽑는다.
    단위테스트 코어(run_route_eval/score_routes)에서 LLM 을 분리하기 위해 별도 함수로 둔다.
    """
    from core.config import load_config
    from core.llm.factory import create_llm
    from app.graph.nodes.router import router_node

    llm = create_llm(load_config())

    def predict(question: str) -> str:
        out = router_node({"question": question, "chat_history": []}, llm=llm)
        return out["route"]

    return predict


if __name__ == "__main__":
    # 라이브 route eval: 실 LLM 필요. python -m tests.eval.runner
    run_route_eval(_live_predict_route(), label="live router_node")

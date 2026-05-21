import os
import time
from typing import Any

import yaml

from shared.models import Answer
from shared.observability.eval.evaluator import EvalCase, Evaluator


def _load_workflow_run():
    from workflows.pipeline.qa import run
    return run


def run_all(question: str) -> dict[str, dict[str, Any]]:
    """단일 질문을 pipeline 워크플로우로 실행 (deprecated 워크플로우 제거 후)."""
    run = _load_workflow_run()
    start = time.time()
    answer: Answer = run(question)
    elapsed = time.time() - start
    return {"pipeline": {"answer": answer, "elapsed_sec": round(elapsed, 2)}}


def print_comparison(question: str, results: dict[str, dict[str, Any]]) -> None:
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"질문: {question}")
    print(f"{sep}\n")
    for mode, data in results.items():
        answer: Answer = data["answer"]
        print(f"[{mode.upper()}]  ({data['elapsed_sec']}s)")
        print(f"  답변: {answer.text}")
        print(f"  출처: {', '.join(answer.sources) or '없음'}")
        if answer.trace:
            print(f"  trace ({len(answer.trace)}단계):")
            for step in answer.trace:
                print(f"    {step}")
        print()


def load_questions(yaml_path: str | None = None) -> list[dict]:
    path = yaml_path or os.path.join(os.path.dirname(__file__), "questions.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def run_eval(yaml_path: str | None = None) -> None:
    """questions.yaml 전체를 Evaluator로 채점하고 결과 출력."""
    raw = load_questions(yaml_path)
    cases = [
        EvalCase(
            question=q["question"],
            expected_keywords=q.get("expected_keywords", []),
            expected_source=q.get("expected_source", ""),
        )
        for q in raw
    ]
    run = _load_workflow_run()
    report = Evaluator(k=5).evaluate(run, cases)

    print("\n=== EVAL REPORT ===")
    for c in report.cases:
        line = f"Q: {c['question']!s:<40}"
        if "error" in c:
            line += f"  ERROR: {c['error']}"
        else:
            line += f"  recall@5={c['recall_at_k']:.2f}  src={c.get('sources')}"
        print(line)
    print(f"\nAggregate: {report.aggregate}")

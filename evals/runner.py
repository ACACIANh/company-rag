import importlib.util
import os
import sys
import time
from typing import Any

import yaml

from shared.models import Answer

# Task 15 will repopulate with new pipeline workflow paths.
_WORKFLOW_PATHS = {}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_workflow(mode: str):
    qa_path = os.path.join(_ROOT, _WORKFLOW_PATHS[mode])
    workflow_dir = os.path.dirname(qa_path)
    sys.path.insert(0, workflow_dir)
    spec = importlib.util.spec_from_file_location(f"qa_{mode}", qa_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def run_all(question: str) -> dict[str, dict[str, Any]]:
    results = {}
    for mode in _WORKFLOW_PATHS:
        module = _load_workflow(mode)
        start = time.time()
        answer: Answer = module.run(question)
        elapsed = time.time() - start
        results[mode] = {"answer": answer, "elapsed_sec": round(elapsed, 2)}
    return results


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

"""route 정확도 채점 (ADR-0022 Decision 3).

questions.yaml 의 expected_route 라벨 어휘는 {"doc_search", "tool_call"} 이고,
라우터(router_node)가 반환하는 현재 route 어휘는 {"doc_search", "agent", "capability", "clarify"} 다.
ADR-0031 에서 tool_call → agent 로 개명됐으므로 라벨 "tool_call" 을 predicted "agent" 와 동치로 취급한다.
정규화는 아래 _EXPECTED_ALIASES 한 곳에만 명시한다.
"""
from collections import defaultdict
from dataclasses import dataclass, field

# expected 라벨 → predicted route 어휘 정규화 (명시·문서화된 동치 맵).
# ADR-0031 에서 tool_call 이 agent 로 개명됨.
_EXPECTED_ALIASES = {
    "tool_call": "agent",
}


def normalize_expected(expected_route: str) -> str:
    """expected 라벨을 predicted route 어휘로 정규화."""
    return _EXPECTED_ALIASES.get(expected_route, expected_route)


@dataclass
class RouteEvalReport:
    accuracy: float
    n_cases: int
    n_correct: int
    # confusion[expected_normalized][predicted] = count
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)


def score_routes(pairs: list[tuple[str, str]]) -> RouteEvalReport:
    """(predicted_route, expected_route) 쌍들을 채점.

    expected_route 는 normalize_expected 로 정규화한 뒤 predicted 와 비교한다.
    반환: 전체 accuracy + expected(정규화)×predicted 혼동행렬 카운트.
    """
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    n_correct = 0
    for predicted, expected in pairs:
        exp = normalize_expected(expected)
        confusion[exp][predicted] += 1
        if predicted == exp:
            n_correct += 1
    n_cases = len(pairs)
    accuracy = n_correct / n_cases if n_cases else 0.0
    return RouteEvalReport(
        accuracy=accuracy,
        n_cases=n_cases,
        n_correct=n_correct,
        confusion={k: dict(v) for k, v in confusion.items()},
    )


def format_route_report(report: RouteEvalReport, label: str = "") -> str:
    """혼동행렬 + accuracy 를 사람이 읽을 텍스트 리포트로."""
    header = f"=== ROUTE EVAL{f' [{label}]' if label else ''} ==="
    lines = [header]
    # 행=expected(정규화), 열=predicted. 열 어휘는 등장한 predicted 의 합집합.
    predicted_labels = sorted(
        {p for row in report.confusion.values() for p in row}
    )
    expected_labels = sorted(report.confusion)
    col_w = max([len("expected\\pred")] + [len(p) for p in predicted_labels] + [8])
    head = "expected\\pred".ljust(col_w) + "".join(p.rjust(col_w) for p in predicted_labels)
    lines.append(head)
    for exp in expected_labels:
        row = report.confusion[exp]
        cells = "".join(str(row.get(p, 0)).rjust(col_w) for p in predicted_labels)
        lines.append(exp.ljust(col_w) + cells)
    lines.append(
        f"\naccuracy={report.accuracy:.3f}  correct={report.n_correct}/{report.n_cases}"
    )
    return "\n".join(lines)

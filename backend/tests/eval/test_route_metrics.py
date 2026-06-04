"""route 채점 함수 단위테스트 (오프라인, LLM 불필요)."""
from tests.eval.route_metrics import (
    normalize_expected,
    score_routes,
)
from tests.eval.runner import run_route_eval


def test_normalize_expected_aliases_tool_call_to_agent():
    assert normalize_expected("tool_call") == "agent"
    assert normalize_expected("doc_search") == "doc_search"
    assert normalize_expected("agent") == "agent"


def test_all_correct_accuracy_and_confusion():
    pairs = [
        ("doc_search", "doc_search"),
        ("doc_search", "doc_search"),
        ("agent", "tool_call"),  # tool_call 정규화 → agent, 정답
    ]
    report = score_routes(pairs)
    assert report.accuracy == 1.0
    assert report.n_correct == 3
    assert report.n_cases == 3
    assert report.confusion["doc_search"]["doc_search"] == 2
    # tool_call 은 agent 로 정규화되어 expected 행 키는 "agent"
    assert report.confusion["agent"]["agent"] == 1


def test_all_misrouted_accuracy_zero():
    pairs = [
        ("agent", "doc_search"),
        ("doc_search", "tool_call"),  # 정규화 → agent expected, predicted doc_search
    ]
    report = score_routes(pairs)
    assert report.accuracy == 0.0
    assert report.n_correct == 0
    assert report.n_cases == 2
    assert report.confusion["doc_search"]["agent"] == 1
    assert report.confusion["agent"]["doc_search"] == 1


def test_tool_call_normalization_treated_as_agent():
    # expected tool_call vs predicted agent 는 정답으로 카운트되어야 한다.
    pairs = [("agent", "tool_call")]
    report = score_routes(pairs)
    assert report.accuracy == 1.0
    assert report.confusion == {"agent": {"agent": 1}}


def test_unknown_predicted_route_counts_as_miss():
    # 라우터가 미지의/예상 밖 route(예: capability, clarify)를 내면 오답으로 집계.
    pairs = [
        ("capability", "doc_search"),
        ("clarify", "tool_call"),
    ]
    report = score_routes(pairs)
    assert report.accuracy == 0.0
    assert report.n_correct == 0
    assert report.confusion["doc_search"]["capability"] == 1
    assert report.confusion["agent"]["clarify"] == 1


def test_empty_pairs_accuracy_zero_no_crash():
    report = score_routes([])
    assert report.accuracy == 0.0
    assert report.n_cases == 0
    assert report.confusion == {}


def test_run_route_eval_injected_predict_offline(capsys):
    # predict 콜러블 주입으로 LLM 없이 종단 채점 경로 검증.
    # 모든 doc_search 질문은 "doc_search", 그 외(tool_call 라벨)는 "agent" 로 맞춘 perfect predictor.
    def predict(question: str) -> str:
        # questions.yaml 의 tool_call 6문항 키워드로 분기하는 대신,
        # 라벨을 모르는 채로도 perfect 가 되도록 expected 를 흉내내는 게 아니라
        # 단순히 doc_search 를 기본으로 두고 tool_call 질문만 agent 로.
        tool_markers = ["예약", "슬랙", "잔여", "메일", "캘린더", "Jira"]
        return "agent" if any(m in question for m in tool_markers) else "doc_search"

    report = run_route_eval(predict, label="offline-perfect")
    # questions.yaml: 24 doc_search + 6 tool_call = 30, 위 predictor 는 전부 정답.
    assert report.n_cases == 30
    assert report.accuracy == 1.0
    out = capsys.readouterr().out
    assert "ROUTE EVAL" in out
    assert "accuracy=1.000" in out

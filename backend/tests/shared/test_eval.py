from core.observability.eval.metrics import keyword_hit_rate, latency_ms, mrr, recall_at_k
from core.observability.eval.evaluator import Evaluator, EvalCase, EvalReport
from core.observability.tracer import Span
from core.models import Answer


def test_recall_at_k_hit():
    assert recall_at_k(["a.md", "b.md", "c.md"], "b.md", k=3) == 1.0


def test_recall_at_k_miss():
    assert recall_at_k(["a.md", "b.md"], "c.md", k=2) == 0.0


def test_recall_at_k_outside_k():
    assert recall_at_k(["a.md", "b.md", "c.md"], "c.md", k=2) == 0.0


def test_latency_ms_from_span():
    s = Span(name="x", started_at=10.0, ended_at=10.250)
    assert round(latency_ms(s)) == 250


def test_keyword_hit_rate_all_present():
    assert keyword_hit_rate("연차는 15일입니다", ["연차", "15일"]) == 1.0


def test_keyword_hit_rate_partial():
    assert keyword_hit_rate("연차는 15일입니다", ["연차", "없는단어"]) == 0.5


def test_keyword_hit_rate_empty_keywords():
    assert keyword_hit_rate("아무 텍스트", []) == 1.0


def test_mrr_first_rank():
    assert mrr(["a.md", "b.md", "c.md"], "a.md") == 1.0


def test_mrr_second_rank():
    assert abs(mrr(["a.md", "b.md", "c.md"], "b.md") - 0.5) < 1e-9


def test_mrr_miss():
    assert mrr(["a.md", "b.md"], "z.md") == 0.0


def test_mrr_empty_expected():
    assert mrr(["a.md"], "") == 0.0


def test_evaluator_includes_mrr_and_multi_k():
    cases = [EvalCase(question="q1", expected_keywords=[], expected_source="a.md")]

    def fake_workflow(_q):
        return Answer(text="", sources=["x.md", "a.md", "b.md"], trace=None)

    report = Evaluator(k=5, eval_ks=[1, 3, 5]).evaluate(fake_workflow, cases)
    c = report.cases[0]
    assert c["recall_at_1"] == 0.0   # a.md는 2위
    assert c["recall_at_3"] == 1.0   # top-3 안에 있음
    assert c["recall_at_5"] == 1.0
    assert abs(c["mrr"] - 0.5) < 1e-9
    assert "mean_mrr" in report.aggregate
    assert "mean_recall_at_3" in report.aggregate


def test_evaluator_runs_all_cases_and_records_metrics():
    cases = [
        EvalCase(question="q1", expected_keywords=["k1"], expected_source="a.md"),
        EvalCase(question="q2", expected_keywords=["k2"], expected_source="b.md"),
    ]

    def fake_workflow(q):
        if q == "q1":
            return Answer(text="k1 here", sources=["a.md"], trace=None)
        return Answer(text="k2 here", sources=["x.md"], trace=None)

    e = Evaluator()
    report = e.evaluate(fake_workflow, cases)

    assert isinstance(report, EvalReport)
    assert len(report.cases) == 2
    assert report.cases[0]["recall_at_k"] == 1.0
    assert report.cases[1]["recall_at_k"] == 0.0


def test_evaluator_continues_on_case_error():
    cases = [
        EvalCase(question="ok", expected_keywords=[], expected_source="a.md"),
        EvalCase(question="boom", expected_keywords=[], expected_source="b.md"),
    ]

    def workflow(q):
        if q == "boom":
            raise RuntimeError("nope")
        return Answer(text="ok", sources=["a.md"], trace=None)

    report = Evaluator().evaluate(workflow, cases)
    assert report.cases[0].get("error") is None
    assert report.cases[1].get("error") == "RuntimeError"

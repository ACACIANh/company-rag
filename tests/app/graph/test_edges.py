from app.graph.edges import route_after_grade, route_after_hallucination


# ─── route_after_grade ───

def test_route_after_grade_goes_to_generate_when_score_high():
    state = {"relevance_score": 0.8, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_goes_to_generate_at_threshold():
    state = {"relevance_score": 0.5, "retry_count": 0}
    assert route_after_grade(state) == "generate"


def test_route_after_grade_retries_when_score_low_and_count_below_limit():
    state = {"relevance_score": 0.3, "retry_count": 0}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_retries_once_more_at_count_1():
    state = {"relevance_score": 0.1, "retry_count": 1}
    assert route_after_grade(state) == "rewrite_retry"


def test_route_after_grade_forces_generate_when_retry_limit_reached():
    state = {"relevance_score": 0.0, "retry_count": 2}
    assert route_after_grade(state) == "generate"


# ─── route_after_hallucination ───

def test_route_after_hallucination_ends_when_passed():
    state = {"hallucination_passed": True, "retry_count": 0}
    assert route_after_hallucination(state) == "end"


def test_route_after_hallucination_retries_when_failed_and_count_below_limit():
    state = {"hallucination_passed": False, "retry_count": 0}
    assert route_after_hallucination(state) == "generate"


def test_route_after_hallucination_ends_when_retry_limit_reached():
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"


def test_route_after_hallucination_ends_after_two_grade_retries_and_one_halluc_retry():
    # grade 2회 + hallucination 1회 → retry_count=3 → 종료
    state = {"hallucination_passed": False, "retry_count": 3}
    assert route_after_hallucination(state) == "end"

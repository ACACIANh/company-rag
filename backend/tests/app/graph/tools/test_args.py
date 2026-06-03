from app.graph.tools._args import single_text_arg


def test_prefers_named_key():
    assert single_text_arg({"question": "Q", "__arg1": "X"}, prefer="question") == "Q"


def test_falls_back_to_arg1_when_named_missing():
    assert single_text_arg({"__arg1": "전직원 급여"}, prefer="question") == "전직원 급여"


def test_falls_back_to_single_value():
    assert single_text_arg({"weird_key": "값"}, prefer="question") == "값"


def test_returns_empty_for_empty_args():
    assert single_text_arg({}, prefer="instruction") == ""

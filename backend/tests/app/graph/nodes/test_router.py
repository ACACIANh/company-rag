from unittest.mock import MagicMock

from app.graph.nodes.router import router_node


def test_router_sets_doc_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"rewritten_question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_router_sets_web_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "web_search"

    result = router_node({"rewritten_question": "최신 LangGraph 업데이트 알려줘"}, llm=mock_llm)

    assert result["route"] == "web_search"
    assert result["tool_input"] == ""


def test_router_sets_tool_call_route_and_tool_input():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "tool_call"

    result = router_node({"rewritten_question": "회의실 예약해줘"}, llm=mock_llm)

    assert result["route"] == "tool_call"
    assert result["tool_input"] == "회의실 예약해줘"


def test_router_falls_back_to_doc_search_on_unknown_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "알 수 없는 응답"

    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["route"] == "doc_search"


def test_router_prompt_includes_question():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    router_node({"rewritten_question": "핵심 질문 내용"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "핵심 질문 내용" in prompt


def test_router_outputs_rewrite_strategy_none():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none"

    result = router_node({"rewritten_question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"


def test_router_outputs_rewrite_strategy_multi_query():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:multi_query"

    result = router_node({"rewritten_question": "연차와 병가의 차이를 비교해줘"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "multi_query"


def test_router_strategy_defaults_to_none_on_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:invalid_strategy"

    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)

    assert result["rewrite_strategy"] == "none"


def test_router_web_search_has_none_strategy():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "web_search:none"

    result = router_node({"rewritten_question": "최신 뉴스"}, llm=mock_llm)

    assert result["route"] == "web_search"
    assert result["rewrite_strategy"] == "none"


def test_router_backward_compat_single_word_response():
    """구형 LLM이 전략 없이 route만 반환해도 동작해야 한다."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"rewritten_question": "연차"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"

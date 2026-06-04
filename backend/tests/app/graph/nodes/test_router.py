from unittest.mock import MagicMock

from app.graph.nodes.router import router_node


def test_router_returns_route_confidence_field():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.9"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert "route_confidence" in result


def test_router_sets_doc_search_route():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_router_sets_agent_route_and_tool_input():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "agent"

    result = router_node({"question": "회의실 예약해줘"}, llm=mock_llm)

    assert result["route"] == "agent"
    assert result["tool_input"] == "회의실 예약해줘"


def test_router_falls_back_to_doc_search_on_unknown_response():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "알 수 없는 응답"

    result = router_node({"question": "질문"}, llm=mock_llm)

    assert result["route"] == "doc_search"


def test_router_prompt_includes_question():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    router_node({"question": "핵심 질문 내용"}, llm=mock_llm)

    prompt = mock_llm.complete.call_args[0][0]
    assert "핵심 질문 내용" in prompt


def test_router_outputs_rewrite_strategy_none():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none"

    result = router_node({"question": "연차 정책이 뭐야?"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"


def test_router_outputs_rewrite_strategy_multi_query():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:multi_query"

    result = router_node({"question": "연차와 병가의 차이를 비교해줘"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "multi_query"


def test_router_strategy_defaults_to_none_on_unknown():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:invalid_strategy"

    result = router_node({"question": "질문"}, llm=mock_llm)

    assert result["rewrite_strategy"] == "none"


def test_router_backward_compat_single_word_response():
    """구형 LLM이 전략 없이 route만 반환해도 동작해야 한다."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search"

    result = router_node({"question": "연차"}, llm=mock_llm)

    assert result["route"] == "doc_search"
    assert result["rewrite_strategy"] == "none"


def test_router_decides_on_original_question_not_rewritten():
    """라우팅은 원본 question으로 판정한다(rewrite 비결정성 차단). (ADR-0031)"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "agent"
    state = {"question": "alice를 추가해줘", "rewritten_question": "추가 절차와 방법은 무엇인가요?"}
    router_node(state, llm=mock_llm)
    prompt = mock_llm.complete.call_args[0][0]
    assert "alice를 추가해줘" in prompt
    assert "추가 절차와 방법은 무엇인가요?" not in prompt


def test_router_parses_confidence_score():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.9"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert result["route"] == "doc_search"
    assert result["route_confidence"] == 0.9


def test_router_triggers_clarify_when_low_confidence_doc_search():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.6"
    result = router_node({"question": "연차 어떻게 해?"}, llm=mock_llm)
    assert result["route"] == "clarify"
    assert result["route_confidence"] == 0.6


def test_router_triggers_clarify_when_low_confidence_agent():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "agent:none:0.5"
    result = router_node({"question": "데이터 보여줘"}, llm=mock_llm)
    assert result["route"] == "clarify"


def test_router_no_clarify_for_capability_regardless_of_confidence():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "capability:none:0.3"
    result = router_node({"question": "뭐 할 수 있어?"}, llm=mock_llm)
    assert result["route"] == "capability"


def test_router_no_clarify_at_exact_threshold():
    """확신도 == 0.75이면 clarify 미트리거."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:0.75"
    result = router_node({"question": "연차 정책"}, llm=mock_llm)
    assert result["route"] == "doc_search"


def test_router_defaults_confidence_to_1_when_missing():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none"
    result = router_node({"question": "연차"}, llm=mock_llm)
    assert result["route_confidence"] == 1.0


def test_router_handles_invalid_confidence_gracefully():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "doc_search:none:abc"
    result = router_node({"question": "연차"}, llm=mock_llm)
    assert result["route_confidence"] == 1.0
    assert result["route"] == "doc_search"

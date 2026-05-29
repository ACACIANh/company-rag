from unittest.mock import MagicMock
from app.graph.nodes.router import router_node


def test_router_handles_uppercase():
    """Test that router converts LLM output to lowercase before validation"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "DOC_SEARCH"
    result = router_node({"rewritten_question": "테스트"}, llm=mock_llm)
    assert result["route"] == "doc_search"


def test_router_strips_whitespace():
    """Test that router strips whitespace from LLM output"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "  web_search  "
    result = router_node({"rewritten_question": "테스트"}, llm=mock_llm)
    assert result["route"] == "web_search"


def test_router_handles_empty_response():
    """Test graceful fallback on empty response"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = ""
    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)
    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_router_handles_garbage_response():
    """Test graceful fallback on garbage response"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "random_garbage_xyz"
    result = router_node({"rewritten_question": "질문"}, llm=mock_llm)
    assert result["route"] == "doc_search"


def test_router_never_sets_tool_input_for_non_tool_call():
    """Ensure tool_input is empty for doc_search and web_search"""
    for route_response in ["doc_search", "web_search"]:
        mock_llm = MagicMock()
        mock_llm.complete.return_value = route_response
        result = router_node({"rewritten_question": "질문"}, llm=mock_llm)
        assert result["tool_input"] == "", f"tool_input should be empty for {route_response}"

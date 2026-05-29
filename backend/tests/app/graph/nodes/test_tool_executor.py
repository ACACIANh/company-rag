from shared.models import SearchResult
from app.graph.nodes.tool_executor import tool_executor_node


def test_tool_executor_returns_search_result_list():
    result = tool_executor_node({"tool_input": "회의실 A 예약", "rewritten_question": "회의실 예약"})

    assert "documents" in result
    assert isinstance(result["documents"], list)
    assert len(result["documents"]) == 1
    assert isinstance(result["documents"][0], SearchResult)


def test_tool_executor_result_source_is_mock_tool():
    result = tool_executor_node({"tool_input": "임의 요청", "rewritten_question": "임의 요청"})

    assert result["documents"][0].chunk.source == "mock-tool"


def test_tool_executor_result_score_is_one():
    result = tool_executor_node({"tool_input": "요청", "rewritten_question": "요청"})

    assert result["documents"][0].score == 1.0


def test_tool_executor_uses_tool_input_in_response():
    result = tool_executor_node({"tool_input": "캘린더 조회", "rewritten_question": "일정 알려줘"})

    assert "캘린더" in result["documents"][0].chunk.text


def test_tool_executor_falls_back_to_rewritten_question():
    result = tool_executor_node({"tool_input": "", "rewritten_question": "미팅 시간 변경해줘"})

    assert "미팅 시간 변경해줘" in result["documents"][0].chunk.text

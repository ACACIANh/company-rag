from unittest.mock import patch

from app.graph.nodes.clarify import clarify_node


def test_clarify_node_maps_doc_search_label():
    with patch("app.graph.nodes.clarify.interrupt", return_value="사내 문서 검색 (RAG)"):
        result = clarify_node({"question": "연차 어떻게 해?"})
    assert result["route"] == "doc_search"
    assert result["tool_input"] == ""


def test_clarify_node_maps_agent_label_and_sets_tool_input():
    with patch("app.graph.nodes.clarify.interrupt", return_value="업무 DB·권한 처리 (에이전트)"):
        result = clarify_node({"question": "연차 어떻게 해?"})
    assert result["route"] == "agent"
    assert result["tool_input"] == "연차 어떻게 해?"


def test_clarify_node_interrupt_payload_includes_question():
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return "사내 문서 검색 (RAG)"

    with patch("app.graph.nodes.clarify.interrupt", side_effect=fake_interrupt):
        clarify_node({"question": "연차 어떻게 해?"})

    assert "연차 어떻게 해?" in captured["payload"]["message"]


def test_clarify_node_interrupt_options_are_korean():
    captured = {}

    def fake_interrupt(payload):
        captured["payload"] = payload
        return "사내 문서 검색 (RAG)"

    with patch("app.graph.nodes.clarify.interrupt", side_effect=fake_interrupt):
        clarify_node({"question": "질문"})

    assert set(captured["payload"]["options"]) == {
        "사내 문서 검색 (RAG)",
        "업무 DB·권한 처리 (에이전트)",
    }

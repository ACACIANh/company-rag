from langchain_core.messages import AIMessage, HumanMessage
from app.graph.nodes.agent_answer import agent_answer_node


def test_extracts_final_answer_from_last_ai_message():
    state = {"agent_messages": [HumanMessage(content="q"), AIMessage(content="조회 결과 요약")]}
    out = agent_answer_node(state)
    assert out["answer"] == "조회 결과 요약"
    assert out["citations"] == []

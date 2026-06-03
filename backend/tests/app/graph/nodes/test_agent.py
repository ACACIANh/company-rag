from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes.agent import agent_node


def test_agent_seeds_human_message_on_first_turn():
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="", tool_calls=[
        {"name": "query_business_data", "args": {"question": "전직원 급여"}, "id": "call_1"}
    ])
    out = agent_node({"agent_messages": [], "rewritten_question": "전직원 급여 보여줘"}, chat_model=model)
    msgs = out["agent_messages"]
    assert any(isinstance(m, HumanMessage) for m in msgs)
    assert any(isinstance(m, AIMessage) for m in msgs)
    sent = model.invoke.call_args[0][0]
    assert any("전직원 급여 보여줘" in getattr(m, "content", "") for m in sent)


def test_agent_appends_ai_message_on_followup_turn():
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="최종 답변")
    out = agent_node(
        {"agent_messages": [HumanMessage(content="q")], "rewritten_question": "q"},
        chat_model=model,
    )
    assert out["agent_messages"][-1].content == "최종 답변"

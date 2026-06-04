from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from app.graph.nodes.agent import agent_node


async def test_agent_seeds_human_message_on_first_turn():
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=AIMessage(content="", tool_calls=[
        {"name": "query_business_data", "args": {"question": "전직원 급여"}, "id": "call_1"}
    ]))
    out = await agent_node({"agent_messages": [], "question": "전직원 급여 보여줘", "rewritten_question": "전직원 급여 조회 방법은?"}, chat_model=model)
    msgs = out["agent_messages"]
    assert any(isinstance(m, HumanMessage) for m in msgs)
    assert any(isinstance(m, AIMessage) for m in msgs)
    sent = model.ainvoke.call_args[0][0]
    # 원본 question으로 시드 — rewritten_question 아님 (ADR-0031)
    assert any("전직원 급여 보여줘" in getattr(m, "content", "") for m in sent)


async def test_agent_seeds_original_question_not_rewritten():
    """첫 진입 시 rewrite(문서검색 편향) 대신 원본 question으로 시드한다 (ADR-0031)."""
    captured = {}

    class _Model:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="ok")

    state = {"question": "alice를 engineering 부서에 추가해줘",
             "rewritten_question": "추가 절차와 방법은 무엇인가요?",
             "agent_messages": []}
    await agent_node(state, chat_model=_Model())
    humans = [m for m in captured["messages"] if isinstance(m, HumanMessage)]
    assert humans and humans[0].content == "alice를 engineering 부서에 추가해줘"


async def test_agent_appends_ai_message_on_followup_turn():
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))
    out = await agent_node(
        {"agent_messages": [HumanMessage(content="q")], "rewritten_question": "q"},
        chat_model=model,
    )
    assert out["agent_messages"][-1].content == "최종 답변"

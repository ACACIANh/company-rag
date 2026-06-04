"""ReAct 에이전트 노드 (ADR-0023). chat 모델이 도구를 선택하거나 최종 답변을 낸다.

chat_model은 build_graph에서 create_chat_llm(cfg).bind_tools(tool_defs)로 주입된다.
첫 진입이면 시스템 지시 + 대화 이력 + 사용자 질문을 agent_messages에 시드한다.
반환은 add_messages 리듀서가 누적한다.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

_SYSTEM = (
    "너는 사내 업무 DB 조회를 돕는 에이전트다. 필요하면 제공된 도구를 호출하고, "
    "도구 결과가 충분하면 한국어로 최종 답변을 작성한다. 도구 없이 답할 수 있으면 바로 답한다. "
    "도구에서 받은 마크다운 표는 변형 없이 그대로 답변에 포함한다."
)


async def agent_node(state: dict, *, chat_model) -> dict:
    messages = list(state.get("agent_messages") or [])
    seeded: list = []
    if not messages:
        # 에이전트는 원본 질문으로 행동 — rewrite(문서검색 편향)가 도구 호출을 흐리지 않게 (ADR-0031)
        question = state.get("question") or state.get("rewritten_question", "")
        # 멀티턴 맥락: user + assistant 모두 포함해 이전 답변을 참고해 도구 호출 결정
        history = state.get("chat_history", [])
        history_msgs = [
            HumanMessage(content=m["content"]) if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in history
        ]
        seeded = [SystemMessage(content=_SYSTEM), *history_msgs, HumanMessage(content=question)]
        messages = seeded
    ai: AIMessage = await chat_model.ainvoke(messages)
    return {"agent_messages": [*seeded, ai]}

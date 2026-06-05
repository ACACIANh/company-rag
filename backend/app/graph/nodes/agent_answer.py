"""에이전트 최종 답변 추출 노드 (ADR-0023).

도구 호출 없이 끝난 에이전트 루프의 마지막 AIMessage 내용을 answer로 싣는다.
SQL 도구 결과는 이미 agent_messages에 반영돼 LLM이 요약했으므로 별도 generate 불필요.
tool_gate_node가 answer를 직접 설정한 경우(구조화 도구 결과)는 그대로 유지한다.
"""
from langchain_core.messages import AIMessage


def agent_answer_node(state: dict) -> dict:
    if state.get("answer"):
        return {"citations": []}
    text = ""
    for m in reversed(state.get("agent_messages") or []):
        if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
            text = m.content
            break
    return {"answer": text, "citations": []}

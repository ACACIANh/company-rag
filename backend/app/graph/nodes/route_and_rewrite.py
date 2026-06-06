"""라우팅 + 질의재작성 동시 실행 노드 (ADR-0055 후속).

router_node와 rewrite_query_node는 둘 다 `state["question"]`+chat_history만 입력으로
쓰고(ADR-0031: 라우팅은 원본 질문 기준) 서로 다른 상태 키를 반환한다 — 의미상 독립.
기존엔 그래프에서 순차(rewrite→router)로 두 번의 LLM 왕복을 직렬화했다.

여기서 두 노드를 `asyncio.to_thread`로 각각 스레드에 올려 `asyncio.gather`로 동시 실행한다
(LLMClient.complete는 동기 블로킹 호출이라 스레드로 띄워야 실제 병렬이 된다). wall-clock이
sum(rewrite, router) → max(rewrite, router)로 줄어든다. 출력 키가 분리돼 단순 병합으로 합친다.
"""
import asyncio

from core.llm.base import LLMClient
from app.graph.nodes.rewrite_query import rewrite_query_node
from app.graph.nodes.router import router_node


async def route_and_rewrite_node(state: dict, *, llm: LLMClient) -> dict:
    rewrite_out, router_out = await asyncio.gather(
        asyncio.to_thread(rewrite_query_node, state, llm=llm),
        asyncio.to_thread(router_node, state, llm=llm),
    )
    # 키 분리(router: route/route_confidence/rewrite_strategy/tool_input,
    # rewrite: rewritten_question) — 단순 병합으로 충돌 없음.
    return {**rewrite_out, **router_out}

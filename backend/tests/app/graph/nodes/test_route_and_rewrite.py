"""route_and_rewrite_node — 라우팅+재작성 동시 실행 노드 테스트.

병렬성은 threading.Barrier(2)로 강제 검증한다: 두 LLM 호출이 동시에 도착해야 barrier가
풀린다. 순차 구현이면 한 스레드만 도착해 timeout → BrokenBarrierError로 테스트가 실패한다.
"""
import threading

import pytest

from app.graph.nodes.route_and_rewrite import route_and_rewrite_node


class _BarrierLLM:
    """두 complete 호출이 동시 실행돼야만 통과(barrier). 순차면 timeout으로 실패."""

    def __init__(self, response: str = "agent:none:0.9") -> None:
        self._barrier = threading.Barrier(2, timeout=5)
        self._response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        self._barrier.wait()  # 동시 도착 못하면 BrokenBarrierError
        return self._response


@pytest.mark.asyncio
async def test_runs_router_and_rewrite_concurrently_and_merges():
    llm = _BarrierLLM(response="agent:none:0.9")
    state = {"question": "내 권한 뭐야", "chat_history": []}

    out = await route_and_rewrite_node(state, llm=llm)

    assert len(llm.prompts) == 2          # 두 LLM 호출이 모두 실행(동시 도착으로 barrier 통과)
    # router 출력 병합
    assert out["route"] == "agent"
    assert out["route_confidence"] == 0.9
    assert out["tool_input"] == "내 권한 뭐야"   # route==agent → 원본 질문
    # rewrite 출력 병합(키 충돌 없음)
    assert "rewritten_question" in out


@pytest.mark.asyncio
async def test_merge_keeps_each_nodes_output_distinct():
    """프롬프트 종류별로 다른 응답을 줘도, rewrite/router 출력이 각자 자리에 병합된다."""

    class _SplitLLM:
        def complete(self, prompt: str) -> str:
            if "명료화" in prompt:            # REWRITE_QUERY 프롬프트
                return "재작성된 질문"
            return "doc_search:multi_query:0.95"   # ROUTER_PROMPT 프롬프트

    out = await route_and_rewrite_node(
        {"question": "온보딩 절차", "chat_history": []}, llm=_SplitLLM()
    )
    assert out["rewritten_question"] == "재작성된 질문"
    assert out["route"] == "doc_search"
    assert out["rewrite_strategy"] == "multi_query"
    assert out["route_confidence"] == 0.95

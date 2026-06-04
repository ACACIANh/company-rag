# ADR-0038: 재질문 앵무새 버그 — chat_history가 생성 답변을 지배하는 문제

> **Status**: 🟢 적용완료

**Date**: 2026-06-04
**Context**: 동일 주제로 재질문하면 직전 답변을 반복(앵무새)하는 버그. `RAG_GENERATE` 프롬프트의 `{chat_history}` 블록에 이전 `assistant` 답변이 포함되고, 유사한 follow-up 질문에서 LLM이 새 문서보다 이 이전 답변을 근거로 삼아 복사·재출력한다.

```
# 현재 프롬프트 순서
이전 대화: {chat_history}   ← assistant 이전 답변 포함
참고 문서: {context}
질문: {question}
```

LLM이 "이전 대화"를 먼저 읽고 유사 질문이 오면 문서보다 history를 우선 참조한다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. `RAG_GENERATE`에서 `chat_history`의 assistant 메시지 제거 — user 턴만 포함 | history 참조 오용 차단, "그것" 같은 지시 대명사 해소는 rewrite_query에 위임 |
| B. 프롬프트 순서 변경 — context를 chat_history 앞으로 이동 | 순서만 바꿔도 문서 우선도 증가, 그러나 긴 context에선 효과 불명확 |
| C. `generate_node` 내 history 길이 상한 축소 (현재 MAX_TURNS=10 → 2~3) | 단기 완화, 근본 원인 미해결 |
| D. `chat_history`를 `generate_node`에서 완전 제거 (rewrite_query에서만 사용) | 가장 단순, 그러나 "아까 말한 것처럼" 류의 맥락 연결 답변 불가 |

## Decision
**선택: A — `RAG_GENERATE` chat_history에서 assistant 메시지 제거**

## Rationale
앵무새 버그의 직접 원인은 LLM이 `assistant` 이전 답변을 "이미 검증된 답"으로 해석해 재사용하는 것이다. `user` 메시지만 남기면 대화 맥락(지시 대명사, 주제 연속성)은 유지하면서 이전 답변 복사를 차단할 수 있다.

`rewrite_query_node`는 `chat_history` 전체(user+assistant)로 이미 의도를 명료화하므로, `generate_node` 단계에서는 user 발화만으로 충분하다.

구현 포인트:
1. `generate_node` — `history_text` 구성 시 `role == "user"` 만 포함:
   ```python
   history_text = "\n".join(
       f"user: {m['content']}" for m in history if m["role"] == "user"
   ) if history else "없음"
   ```
2. 동일 버그가 `agent_node`에도 잠재 — agent는 현재 `chat_history` 미사용이므로 해당 없음
3. 회귀 검증: `tests/eval/runner.py`로 follow-up 시나리오 점수 확인

# ADR-0024: HITL 종단 완결 — 계획된 동작 노출 + API resume 루프

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: ADR-0027의 JUSTIFY_AND_APPROVE는 `interrupt()`로 사유를 받지만, 그 interrupt를 **실제 API로 재개하는 경로가 없었다**(`app/api`에 resume 처리 0건) — HITL 게이트가 테스트에서만 동작하고 실서비스 종단에서는 미완성이었다. ADR-0023의 에이전트 루프 위에서 이 종단을 메운다. 설계: `docs/superpowers/specs/2026-06-03-tool-call-agentification-design.md`.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| 별도 resume 엔드포인트(예: `/chat/{id}/resume`) | 명시적이나 프론트·세션 흐름에 신규 계약 추가, 라우팅·인증 중복 |
| **다음 사용자 메시지를 사유로 해석** | interrupt 상태 스레드에 들어온 다음 메시지를 `Command(resume=메시지)`로 재개. 신규 엔드포인트 0개, 기존 `/chat`·`/chat/stream`이 그대로 동작. 대화형 UX와 일치 |

## Decision

**선택: interrupt 상태를 감지해 다음 사용자 메시지를 사유로 해석하고 `Command(resume=...)`로 재개한다. interrupt 발생 시 "계획된 동작(SQL)"을 사용자에게 노출한다.**

1. **interrupt 페이로드에 계획 노출**: `confirm_node`가 `interrupt({"message":..., "actions":[{tool, args, planned_action, risk}]})`로 승인 대상(생성된 SQL 등)을 담는다(ADR-0023에서 구현, 본 ADR이 종단 활용).
2. **`answer_question` resume 루프**(`app/graph/builder.py`): `aget_state(config)`로 스레드가 interrupt 상태인지 감지 → 그렇다면 들어온 `question`을 사유로 보고 `Command(resume=question)`로 재개. 아니면 신규 질문 처리. 결과에 `__interrupt__`가 있으면 "사유 회신 필요 + 계획된 SQL"을 담은 답으로 변환(`_interrupt_answer`).
3. **`stream_answer` 동일 분기**: 스트리밍 경로도 같은 감지/재개. interrupt 시 토큰 큐에 `{"type":"interrupt","actions":[...]}` + `done`을 emit하고 종료(세션 저장 안 함 — pending은 체크포인터에 산다).
4. **API 계층 무변경**: `/chat`·`/chat/stream`은 세션별 고정 `thread_id`(`{user_id}:{session_id}`)로 호출하므로, 같은 세션의 후속 메시지가 자동으로 resume 사유로 감지된다. tool_call_id 매칭은 `pending_tool_calls`가 보존한다(SP1은 단일 JUSTIFY 기본 가정, 구조는 멀티 대응).

### 검증된 LangGraph 1.2.0 API
- interrupt 감지: `existing.next and existing.tasks and any(getattr(t, "interrupts", None) for t in existing.tasks)`.
- interrupt 값: `final["__interrupt__"][0].value` = `confirm_node`가 넘긴 dict.

## Rationale

- 외부 승인자 없는 DBA-부재 전제(ADR-0027)에서 "다음 메시지를 사유로" 모델은 self-service 흐름과 정확히 맞고, 신규 엔드포인트·프론트 계약 없이 기존 대화 UX에 얹힌다.
- 계획된 SQL 노출은 "무엇을 승인하는지 모르고 사유를 적는" 맹목 승인을 막는다 — 사유 기재의 감사 가치(ADR-0027)를 실효화.
- 체크포인터(AsyncPostgresSaver)가 이미 thread별 pending 상태를 보존하므로 신규 저장소가 불필요.

## 미해결 / 후속

- **멀티 병렬 JUSTIFY**: 여러 tool_call이 동시에 JUSTIFY일 때의 완전한 사유-매칭 UX는 미구현(SP1은 단일 기본 가정). 필요 시 후속.
- **프론트 연동**: `{"type":"interrupt", actions}` 이벤트를 web가 어떻게 렌더링·사유 입력받을지는 web 측 후속.
- **SP2(권한 관리 도구)**: 본 HITL 종단 위에 `fga_grant_revoke` 고위험 도구 등록 — 별도 스펙.

## 영향받는 결정

- [ADR-0023](ADR-0023-tool-call-agentic-loop.md) — 그 에이전트 루프·confirm 페이로드 위에서 API 종단을 완결.
- [ADR-0027](ADR-0027-justify-and-approve-self-service-gate.md) — JUSTIFY_AND_APPROVE 사유 흐름을 실서비스 종단까지 연결(그동안 끊겨 있던 부채 해소).

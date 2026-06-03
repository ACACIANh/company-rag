# ADR-0030: web interrupt(HITL JUSTIFY) 대화형 렌더링

> **Status**: ⚪ 제안됨   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: ADR-0024가 HITL resume의 API 종단을 메우면서 `{"type":"interrupt", actions}` SSE 이벤트를 방출하지만, "web가 이를 어떻게 렌더링·사유 입력받을지는 web 측 후속"으로 명시 보류했다. SP2b(ADR-0029) `manage_permission`이 grant를 항상 JUSTIFY로 게이트하면서 interrupt가 실서비스에서 자주 발생하는데, web(`/chat/stream`만 사용)은 `interrupt` 이벤트를 처리하지 않아 JUSTIFY가 떠도 화면에 사유 입력 경로가 없다. 이 종단을 web에서 메운다.

## Options

| 선택지 | 트레이드오프 |
|--------|------------|
| **대화형 (기존 입력창 재사용)** | interrupt를 특수 메시지로 표시, 사유는 기존 입력창으로, resume은 기존 `send` 재사용(백엔드가 다음 메시지를 사유로 해석 — ADR-0024). 새 컴포넌트·상태 최소. ADR-0024 대화형 모델과 정확히 일치 |
| 전용 다이얼로그/카드 | `InterruptDialog` 컴포넌트 + 전용 사유 textarea + 실행/취소 버튼. 승인 느낌 명시적이나 컴포넌트·상태·취소 흐름 추가 |

## Decision

**선택: 대화형 렌더링.** interrupt를 특수 assistant 메시지로 표시하고, 사유는 기존 입력창으로 받으며, resume은 기존 `send`를 그대로 재사용한다. 취소는 빈 사유 회신으로 처리한다.

### 구현 범위 (web/)

#### ① 타입 — `web/src/types.ts`
```ts
export interface InterruptAction { tool: string; planned_action: string }

export type SSEEvent =
  | { type: "token";   content: string }
  | { type: "sources"; sources: string[] }
  | { type: "done";    session_id: string }
  | { type: "error";   message: string }
  | { type: "interrupt"; actions: InterruptAction[] }   // 추가

export interface ChatMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
  streaming?: boolean;
  interrupt?: InterruptAction[];   // 추가 — 있으면 JUSTIFY 안내 카드
}
```

#### ② API — `web/src/api/client.ts`
**변경 없음.** `streamChat`의 `JSON.parse(line) as SSEEvent`가 interrupt 이벤트를 그대로 yield한다(타입만 ①에서 확장).

#### ③ ChatPage — `web/src/chat/ChatPage.tsx`
- `awaitingJustification` state 추가(boolean).
- `send` 루프에 `interrupt` 케이스 추가: 특수 assistant 메시지(`{role:"assistant", content:"", interrupt: event.actions}`) push + `setAwaitingJustification(true)`.
- `send` 시작부에서 `setAwaitingJustification(false)`(다음 회신을 보내면 해제 — resume이든 신규 질문이든 백엔드가 thread 상태로 판단).
- resume 전용 코드 없음: interrupt 후 사용자가 입력창에 사유를 치면 기존 `send(사유)`가 그대로 백엔드 `Command(resume=...)`로 이어진다(같은 `sessionId` 유지 — done 이벤트가 sessionId 보존).

#### ④ MessageList — `web/src/chat/MessageList.tsx`
`msg.interrupt`가 있으면 경고 톤 카드를 렌더: 계획된 동작 목록(`SourceBadge` 태그 스타일 재사용으로 `tool` + `planned_action` 표시) + "실행하려면 사유를 입력하세요" 안내 + 작은 **"취소"** 버튼.

#### ⑤ MessageInput — `web/src/chat/MessageInput.tsx`
`awaitingJustification` prop이 true면 placeholder를 "실행 사유를 입력하세요"로 교체(시각적 모드 전환). 기존 전송 로직 불변.

#### ⑥ 취소
interrupt 카드의 "취소" 버튼 → `send("")`(빈 사유). 백엔드 `justify_execute`가 빈 사유를 취소로 처리(기존 구현, ADR-0027). 빈 문자열은 `MessageInput`을 거치지 않고 카드 버튼이 직접 `send`를 호출한다.

## Rationale

- **왜 대화형**: ADR-0024가 resume을 "interrupt 상태 thread의 다음 메시지를 사유로 해석"으로 설계해, 신규 엔드포인트·계약 없이 대화 UX에 얹었다. web도 같은 모델을 따르면 resume 전용 컴포넌트·상태·요청이 전혀 필요 없고, interrupt를 "표시"만 하면 된다. 백엔드 철학과 web이 일관되며 변경 표면이 최소다.
- **왜 특수 메시지(별도 모달 아님)**: 대화 흐름 안에 자연스럽게 녹고, 기존 `MessageList`/`SourceBadge`/`MessageInput` 패턴을 재사용한다. 모달은 승인 느낌이 강하지만 컴포넌트·포커스·취소 상태를 추가로 관리해야 한다(YAGNI).
- **왜 취소=빈 사유**: 백엔드가 이미 빈 사유를 취소로 처리한다. 별도 취소 API가 불필요하고, "사유 없이는 실행 안 됨"(ADR-0027) 규칙과 일치한다.

## Consequences

- web가 `/chat/stream`만 쓰므로 비스트리밍 `/chat`은 무관(테스트 전용).
- interrupt 카드는 `planned_action`(예: `grant user:alice member department:finance`)을 그대로 노출 — 사용자가 무엇을 승인하는지 본다(ADR-0024 "계획 노출"의 web 실현).
- 멀티 액션(`actions` 배열 길이 >1) 표시는 지원하나, 현재 단일 도구 호출이 기본(ADR-0023 보류 항목과 동일 가정).
- **범위 밖**: SQL JUSTIFY(query_business_data 대량/PII)도 같은 interrupt 경로라 이 UI가 그대로 적용됨 — 권한 도구 전용이 아니다.

## DoD
1. `ChatPage` 테스트: interrupt 이벤트 수신 → 특수 메시지 렌더 + `awaitingJustification` 전환 / 사유 send → resume 흐름.
2. `MessageList` 테스트: `interrupt` 필드 메시지가 계획된 동작·안내·취소 버튼을 렌더.
3. `MessageInput` 테스트: `awaitingJustification` 시 placeholder 변경.
4. 수동 검증: admin 로그인 → 권한 부여 질문 → 카드 표시 → 사유 입력 → 실행 / 취소 버튼 → 취소.
5. ADR 인덱스 재생성.

## 관련 ADR
- [[ADR-0024]] HITL API resume — 이 UI가 소비하는 interrupt 이벤트·resume 모델의 출처
- [[ADR-0029]] 권한 관리 도구 — interrupt가 자주 발생하는 직접 동기(grant=JUSTIFY)
- [[ADR-0027]] JUSTIFY_AND_APPROVE — 빈 사유=취소 규칙의 근거
- [[ADR-0003]] 프론트엔드 아키텍처 — web 스택·컴포넌트 규약

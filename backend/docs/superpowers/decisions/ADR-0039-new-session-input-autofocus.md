# ADR-0039: "+ 새 대화" 클릭 시 입력창 자동 포커싱

> **Status**: ⚪ 제안됨

**Date**: 2026-06-04
**Context**: `SessionSidebar`의 "+ 새 대화" 버튼을 누르면 세션이 초기화되지만 입력창에 포커스가 이동하지 않아 사용자가 클릭 후 다시 입력창을 클릭해야 한다. 새 대화 시작 = 바로 입력 의도이므로 자동 포커싱이 자연스럽다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. `MessageInput`에 `ref` 노출 → `ChatPage`가 세션 변경 시 `.focus()` 호출 | 컴포넌트 결합 최소화, 명시적 트리거 |
| B. `MessageInput` 내부에서 `autoFocus` 속성 사용 | 마운트 시 1회만 동작 — 세션 전환(언마운트 없음) 시 재발동 안 됨, 불충분 |
| C. 세션 변경 이벤트를 `EventEmitter`/전역 상태로 전파 → `MessageInput`이 구독 | 컴포넌트 분리도 높지만 과설계 |

## Decision
**선택: A — `MessageInput`에 `inputRef` 노출 + `ChatPage`에서 세션 변경 시 `focus()` 호출**

## Rationale
`SessionSidebar → ChatPage → MessageInput` 의 props 흐름이 이미 있으므로 `ref` 전달이 가장 단순하다. `autoFocus`(B)는 컴포넌트 재마운트가 없는 세션 전환에서 동작하지 않아 불충분.

구현 포인트:
1. `MessageInput.tsx` — `useImperativeHandle` + `forwardRef`로 `focus()` 메서드 노출
2. `ChatPage.tsx` — `inputRef = useRef()` 생성, `MessageInput`에 전달
3. 세션 변경 `useEffect([sessionId])` 내에서 `inputRef.current?.focus()` 호출
4. 범위: 프론트엔드 전용, 백엔드 변경 없음

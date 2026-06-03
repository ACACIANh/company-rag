# ADR-0032: 게이트 도구 단일 입력 인자(`__arg1`) 처리

> **Status**: 🟢 적용완료   <!-- 🟢 적용완료 · 🔵 승인됨 · ⚪ 제안됨 · 🟡 보류 · 🟣 대체됨 · ⚫ 폐기 -->

**Date**: 2026-06-03
**Context**: SQL·권한 게이트 도구는 `langchain_core.tools.Tool(func=lambda question: "")` / `lambda instruction: ""`로 정의된 단일 문자열 입력 레거시 Tool이다. `bind_tools`된 모델은 호출 인자를 `{'__arg1': '...'}`로 넘기는데(라이브 invoke로 확인), 두 핸들러의 `plan()`이 `args["question"]`/`args["instruction"]`로 읽어 `KeyError`로 크래시했다(`/chat/stream`에서 `{"type":"error","message":"'question'"}`). 이로 인해 SQL JUSTIFY·권한 JUSTIFY interrupt 경로가 게이트 전에 죽었다.

## Decision
- 공용 헬퍼 `app/graph/tools/_args.py::single_text_arg(args, *, prefer)` 도입. named 키(`prefer`) → `__arg1` → 단일 값 → `""` 순으로 폴백.
- `sql_tool.plan`/`permission_tool.plan`이 이 헬퍼로 단일 NL 입력을 추출. 도구 contract·게이트·실행 로직은 불변.

## Consequences
- 모델이 `__arg1`로 넘겨도 NL 입력을 안정적으로 추출 → 두 게이트 도구가 게이트·interrupt 경로까지 정상 진행.
- ADR-0031(라우팅)과 함께 권한 JUSTIFY가 end-to-end 동작.

## 관련 ADR
- [[ADR-0023]] 게이트된 도구 디스패치 — 이 도구들의 plan/execute 출처
- [[ADR-0029]] manage_permission — 동일 결함 보유, 함께 해소
- [[ADR-0031]] 라우터 agent 라벨 — 함께 권한 JUSTIFY 동작

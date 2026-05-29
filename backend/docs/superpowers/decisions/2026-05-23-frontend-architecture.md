# Decision: 프론트엔드 추가 방향성

**Date**: 2026-05-23
**Context**: company-rag에 사용자용 채팅 프론트엔드를 추가할 때의 범위/레포 구조/기술 스택/인증·스트리밍·스타일링 방식을 결정한다.

## Options

| 영역 | 선택지 | 트레이드오프 |
|------|--------|--------------|
| FE 범위 | A. 채팅 UI만 / B. 채팅+관리자 / C. 채팅·관리자 분리 SPA | A는 가장 작음. B는 /admin 활용도 ↑지만 작업량 1.5~2배. C는 권한 경계 깔끔하지만 이중 빌드. |
| 레포 구조 | A. 같은 레포 `web/` / B. FastAPI StaticFiles 통합 / C. 별도 레포 | A는 Phase/PR 일관. B는 단일 프로세스지만 빌드 라이프사이클 결합. C는 단일 개발자에 과함. |
| 기술 스택 | A. Vite+React+TS / B. Next.js+AI SDK / C. Streamlit | A는 가볍고 탈착 쉬움. B는 SSR 이점이 FastAPI 백엔드에서 안 살아남. C는 가장 빠르지만 venv 오염, 실제 웹 FE 학습 0. |
| 토큰 저장 | A. localStorage / B. httpOnly cookie / C. sessionStorage | A는 가장 단순, XSS 취약. B는 안전하지만 CSRF/CORS credentials 추가 작업. C는 다중 탭 UX 나쁨. |
| 스트리밍 | A. v1 동기 / B. 처음부터 SSE | A는 backend 변경 0. B는 UX 좋지만 backend astream+StreamingResponse+EventSource 일괄 도입 필요. |
| 스타일링 | A. Tailwind / B. 수제 CSS / C. shadcn/ui+Tailwind | A는 클래스 기반 그린필드. B는 의존성 0이지만 확장성 ↓. C는 컴포넌트 코드가 소스 침투해 탈착 어려움. |

## Decision

- **FE 범위**: 사용자용 채팅 UI만
- **레포 구조**: 같은 레포의 `web/` 디렉터리
- **기술 스택**: Vite + React + TypeScript
- **토큰 저장**: localStorage
- **스트리밍**: v1은 동기 응답, SSE는 추후 Phase로 분리
- **스타일링**: Tailwind CSS

## Rationale

- 사용자가 "**가장 단순/빠른 구현 + 추후 완전 삭제 무방한 모듈**"을 명시. → `web/` 디렉터리 단일 격리 + 독립 `package.json` + `rm -rf web/`로 흔적 제거 가능한 조합 우선.
- 백엔드는 이미 `/chat`(JWT Bearer, 동기), `/auth/token`, `/auth/me`, `/admin/*`이 완비 → 풀스택 프레임워크(Next/Streamlit)의 이점이 없음. SPA + 외부 API 호출이 가장 자연스러움.
- 학습 목적 + 단일 개발자: localStorage·동기 응답·Tailwind 모두 "결정 비용 최소, 추후 교체 가능" 기준에 부합. 보안/스트리밍/디자인 시스템은 v2 이후 ADR에서 갱신.
- 백엔드 변경은 **CORS 미들웨어 추가** 한 가지로 최소화. 스트리밍 도입은 별도 Phase로 분리해 backend astream을 도입할 때 같이 결정.

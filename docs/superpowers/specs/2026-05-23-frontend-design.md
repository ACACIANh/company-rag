# Frontend v1 Design Spec

**Date**: 2026-05-23
**Status**: Approved by user (brainstorming session)
**Related ADR**: [2026-05-23-frontend-architecture.md](../decisions/2026-05-23-frontend-architecture.md)

## 1. 목표와 범위

company-rag에 사용자용 채팅 SPA를 추가한다. 백엔드(`/chat`, `/auth/*`)와 결합도를 최소화하고, `web/` 디렉터리 통째로 제거해도 backend가 무손상이도록 격리한다.

**In scope**
- 로그인 화면
- 멀티턴 채팅 화면 (질문 → 답변 + 출처 표시)
- JWT 기반 인증 흐름
- 401 자동 로그아웃, 429 Retry-After 안내

**Out of scope (v1)**
- 응답 스트리밍 (SSE) — 추후 Phase
- 관리자 콘솔 — 별도 결정 시 추가
- 회원가입 / 비밀번호 변경
- 다국어
- 모바일 전용 레이아웃 (반응형 기본만)

## 2. 아키텍처

독립 SPA가 FastAPI를 외부 API로 호출하는 2-tier 구성.

```
[Browser: Vite dev :5173 / built :8000-serve]
     │
     │  fetch(Authorization: Bearer <token>)
     ▼
[FastAPI :8000]
  ├─ POST /auth/token   (username/password → access_token)
  ├─ GET  /auth/me      (현재 user 정보)
  └─ POST /chat         (question + session_id → answer + sources + session_id)

[localStorage]
  - token: string
  - session_id: string  (마지막 채팅 세션 유지용)
```

**불변 조건**
- shared/, app/graph/, app/ingestion/ 등 backend 코어 모듈은 변경 없음.
- backend 단일 변경점: `app/api/chat.py`에 CORS 미들웨어 추가.

## 3. 디렉터리 구조

의존성: `react`, `react-dom`, `react-router-dom`, `tailwindcss`. devDependencies: `vite`, `@vitejs/plugin-react`, `typescript`, `vitest`.

```
web/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .env.example              # VITE_API_BASE_URL=http://localhost:8000
└── src/
    ├── main.tsx
    ├── App.tsx               # react-router-dom: / → /chat, 비인증 시 /login
    ├── index.css             # @tailwind base/components/utilities
    ├── types.ts              # ChatRequest/ChatResponse/AuthUser/TokenResponse
    ├── api/
    │   └── client.ts         # fetch wrapper
    ├── auth/
    │   ├── AuthContext.tsx
    │   └── LoginPage.tsx
    └── chat/
        ├── ChatPage.tsx
        ├── MessageList.tsx
        ├── MessageInput.tsx
        └── SourceBadge.tsx
```

## 4. 컴포넌트 책임

| 컴포넌트 | 책임 | 의존 |
|---------|------|------|
| `client.ts` | 모든 HTTP 통과 지점. Bearer 자동 부착, JSON 직렬화, 에러 정규화 (Network/4xx/5xx 분류) | localStorage |
| `AuthContext` | `{token, user}` 단일 소스. login/logout. 401 수신 시 강제 로그아웃 | client.ts, localStorage |
| `LoginPage` | username/password 폼 → `/auth/token` → 성공 시 `/chat`로 이동 | AuthContext |
| `ChatPage` | `session_id` 유지, 메시지 히스토리 로컬 상태로 관리, `/chat` 호출 | client.ts, MessageList, MessageInput |
| `MessageList` | 메시지 버블 + 답변 하단의 SourceBadge 렌더 | 순수 props |
| `MessageInput` | 텍스트 입력, Enter 전송, 전송 중 disable | 순수 props |
| `SourceBadge` | `sources: string[]`을 칩으로 표시 | 순수 props |

## 5. 데이터 흐름

### 5.1 로그인
1. 사용자가 username/password 입력
2. `POST /auth/token` → `{access_token}` 수신
3. `localStorage.setItem("token", access_token)`
4. `GET /auth/me`로 user 정보 캐시 (AuthContext 상태)
5. `/chat` 라우트로 이동

### 5.2 채팅 (멀티턴)
1. 첫 메시지: `POST /chat {question, session_id: null}` → 응답의 `session_id` 보관
2. 이후 메시지: 같은 `session_id` 재사용
3. 화면 렌더: `answer`는 assistant 버블, `sources`는 그 아래 칩
4. 로그아웃 시 localStorage의 `token`, `session_id` 모두 폐기 + 메시지 히스토리 초기화

### 5.3 401/만료
- client.ts가 401을 감지 → AuthContext에 통보 → 토큰/세션 폐기 → `/login`으로 리디렉트

## 6. 백엔드 변경

`app/api/chat.py` 상단 FastAPI 인스턴스 생성 직후:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=load_config().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`shared/config`에 `cors_origins: list[str] = ["http://localhost:5173"]` 필드 추가.
운영 origin은 `.env`에서 `CORS_ORIGINS=https://...,https://...` 형식으로 오버라이드.

**그 외 backend 파일은 수정하지 않는다.**

## 7. 에러 처리

| 상황 | 처리 |
|------|------|
| 네트워크 실패 / 5xx | 입력 박스 옆 인라인 에러 메시지. 입력 텍스트는 유지. |
| 401 | 토큰·세션 폐기 + `/login` 리디렉트. 토스트 "세션이 만료되었습니다". |
| 429 | `Retry-After` 헤더 값을 읽어 "N초 후 다시 시도하세요" 안내. |
| 빈 sources | "출처를 찾지 못했습니다" 안내 라벨 표시. |
| 빈 answer | 사용자에게 재시도 안내. |

## 8. 테스트 / DoD

**단위 테스트 (Vitest)**
- `client.ts`: Bearer 헤더 부착, 401 처리 콜백 호출
- `AuthContext`: login → state 변경, 401 신호 → 폐기

**수동 통합 테스트 (DoD)**
- backend `uvicorn`과 `web/` `npm run dev`를 동시 실행
- 골든패스: 로그인 → 1턴 질문/답변 → 2턴 질문(컨텍스트 유지 확인) → 로그아웃 → 토큰 만료 시 자동 로그아웃

**회귀**
- `tests/eval/runner.py` 통과, recall@5는 이전 Phase 이상 유지

## 9. 작업 워크플로우

- 브랜치: `feat/frontend-v1`
- 커밋은 이 브랜치에 모음
- PR description에 본 스펙 링크 + DoD 체크리스트:
  - [ ] `web/` 설치/빌드 성공
  - [ ] `npm run build` gzip < 300KB
  - [ ] 골든패스 수동 통과
  - [ ] backend CORS 외 변경 없음
  - [ ] 회귀 테스트 recall@5 유지
- merge 후 태그: `frontend-v1`

## 10. 추후 Phase (참고)

- **frontend-v2 (스트리밍)**: backend `astream` + `StreamingResponse(SSE)` 도입, FE는 `EventSource` 수신.
- **frontend-v3 (관리자 콘솔)**: `/admin/*` API 활용. 권한 분기로 같은 `web/` 안에 라우트 추가 또는 별 SPA로 분리 결정.
- **보안 강화**: localStorage → httpOnly cookie 전환 검토 (CSRF/CORS credentials 동반).

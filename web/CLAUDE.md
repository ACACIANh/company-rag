# web/ — 프론트엔드 안내 (Claude Code용)

`company-rag` 챗봇의 웹 프론트엔드. **이 디렉토리(`web/`)를 작업 디렉토리로 실행한다.**

## 스택

Vite + React 18 + TypeScript + TailwindCSS. 테스트는 Vitest + Testing Library.

## 명령

- 개발 서버: `npm run dev` (port 5173)
- 빌드: `npm run build` (`tsc && vite build`)
- 테스트: `npm test` (`vitest run`) / 워치: `npm run test:watch`
- 환경변수: `.env.example`를 `.env`로 복사. `VITE_API_BASE_URL`은 백엔드 주소 (기본 `http://localhost:8000`).

## 구조

- `src/api/` — 백엔드 API 클라이언트 (`client.ts`). 모든 백엔드 호출은 여기를 경유한다.
- `src/auth/` — 인증 (`AuthContext`, `LoginPage`).
- `src/chat/` — 채팅 UI (`ChatPage`, `MessageList`, `MessageInput`, `SessionSidebar`, `MarkdownRenderer`, `SourceBadge`).
- `src/App.tsx`, `src/main.tsx` — 진입점. 라우팅은 `react-router-dom`.

## 규약

- **테스트는 컴포넌트 옆에** `*.test.tsx`로 둔다 (예: `ChatPage.test.tsx`). 새 컴포넌트·API 함수에는 테스트를 추가한다.
- `tsconfig`는 `strict`, `noUnusedLocals`, `noUnusedParameters`가 켜져 있다. 미사용 변수·import를 남기지 않는다.
- 백엔드와의 통신은 반드시 `src/api/client.ts`를 통한다. 컴포넌트에서 직접 `fetch`하지 않는다.
- 디자인 시스템(컬러 토큰·타이포·레이아웃)은 `DESIGN.md`를 따른다. Tailwind 설정은 `tailwind.config.js`.

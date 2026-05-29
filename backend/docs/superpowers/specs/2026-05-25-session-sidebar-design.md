# Design: 대화 세션 목록 사이드바

**Date**: 2026-05-25
**Status**: Approved

## Overview

왼쪽 토글 사이드바에 대화 세션 목록을 표시한다. 세션 클릭 시 메시지 히스토리를 복원하고, 로그아웃 후 재로그인 시에도 목록이 유지된다. 세션 메타데이터와 메시지는 dev에서 인메모리, prod에서 PostgreSQL에 저장한다.

---

## 1. UI / 레이아웃

- **사이드바 형태**: 토글 방식. 기본 상태는 **열림(open)**. 상단 헤더의 햄버거(☰) 버튼으로 열고 닫는다.
- **사이드바 너비**: 200px (열림) / 0px (닫힘, CSS transition 0.2s)
- **세션 목록**: 날짜 그룹(오늘 / 어제 / 이번 주 / 더 이전)으로 묶어 표시. 그룹 내 최신순 정렬.
- **세션 제목**: 첫 질문 앞 20자 자동 생성. 이후 편집 기능 없음.
- **활성 세션**: `background: #f0efff`, 텍스트 `#533afd` (primary 색상)으로 강조.
- **삭제 버튼**: 세션 아이템 hover 시 🗑 아이콘 표시. 확인 없이 즉시 삭제.
- **새 대화 버튼**: 사이드바 최상단 pill 버튼(`+ 새 대화`).

---

## 2. 백엔드 아키텍처

### 2-1. `shared/session/` 모듈

```
shared/session/
├── base.py          # SessionStore ABC
├── factory.py       # create_session_store(config)
└── adapters/
    ├── memory.py    # InMemorySessionStore
    └── postgres.py  # PostgresSessionStore
```

**`SessionStore` ABC:**

```python
class SessionStore(ABC):
    @abstractmethod
    def create_session(self, thread_id: str, user_id: str, title: str) -> None: ...

    @abstractmethod
    def list_sessions(self, user_id: str) -> list[SessionMeta]: ...

    @abstractmethod
    def get_messages(self, thread_id: str) -> list[StoredMessage]: ...

    @abstractmethod
    def add_message(self, thread_id: str, role: str, content: str, sources: list[str]) -> None: ...

    @abstractmethod
    def delete_session(self, thread_id: str, user_id: str) -> None: ...
```

**데이터 클래스:**

```python
@dataclass
class SessionMeta:
    thread_id: str
    title: str
    created_at: str   # ISO8601

@dataclass
class StoredMessage:
    role: str         # 'user' | 'assistant'
    content: str
    sources: list[str]
```

**`InMemorySessionStore`**: `dict[str, SessionMeta]` + `dict[str, list[StoredMessage]]` 로 관리. 프로세스 재시작 시 소멸.

**`PostgresSessionStore`**: `psycopg2` (또는 `asyncpg`) 사용. 아래 스키마 기반.

### 2-2. PostgreSQL 스키마

```sql
CREATE TABLE sessions (
    thread_id   TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON sessions (user_id, created_at DESC);

CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES sessions(thread_id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    sources     TEXT[] NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

### 2-3. LangGraph 체크포인터

| 환경 | 체크포인터 | 비고 |
|------|-----------|------|
| dev  | `MemorySaver` (현행 유지) | 재시작 시 컨텍스트 소멸 허용 |
| prod | `PostgresSaver` (`langgraph-checkpoint-postgres`) | 동일 PostgreSQL 인스턴스 사용 |

`session_store_type` 설정에 따라 체크포인터도 함께 전환한다.

### 2-4. Config 추가 (`shared/config.py`)

```python
session_store_type: str = "memory"   # "memory" | "postgres"
postgres_dsn: str = ""               # prod: postgresql://user:pass@host/db
```

### 2-5. API 엔드포인트 (`app/api/sessions.py`)

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/sessions` | 현재 유저의 세션 목록 (created_at DESC) |
| `GET` | `/sessions/{session_id}/messages` | 세션의 메시지 히스토리 (created_at ASC) |
| `DELETE` | `/sessions/{session_id}` | 세션 삭제 (본인 세션만, 204 반환) |

### 2-6. `app/api/chat.py` 수정

응답 성공 후:
1. `thread_id`가 신규이면 `session_store.create_session(thread_id, user_id, question[:20])`
2. `session_store.add_message(thread_id, "user", question, [])`
3. `session_store.add_message(thread_id, "assistant", answer, sources)`

`add_message` 실패는 채팅 응답에 영향을 주지 않는다 — 예외를 로그로 기록하고 계속 진행.

---

## 3. 프론트엔드 아키텍처

### 3-1. 파일 구조

```
web/src/
├── types.ts                       # Session, SessionMessage 타입 추가
├── api/client.ts                  # getSessions, getSessionMessages, deleteSession 추가
└── chat/
    ├── SessionSidebar.tsx         # 신규 컴포넌트
    └── ChatPage.tsx               # 수정
```

### 3-2. 새 타입 (`types.ts`)

```typescript
export interface Session {
  thread_id: string;
  title: string;
  created_at: string;  // ISO8601
}

export interface SessionMessage {
  role: ChatRole;
  content: string;
  sources?: string[];
}
```

### 3-3. `SessionSidebar` 컴포넌트

**Props:**
```typescript
interface SessionSidebarProps {
  isOpen: boolean;
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}
```

**동작:**
- `sessions`를 날짜 그룹으로 분류하는 순수 함수 `groupSessionsByDate(sessions)` 내부 사용
- 삭제 클릭 → `onDelete` 호출 (confirm 없음)
- 아이템 hover 시 CSS로 삭제 아이콘 표시 (`opacity: 0 → 1`)

### 3-4. `ChatPage` 상태 추가

```typescript
const [sidebarOpen, setSidebarOpen] = useState(true);
const [sessions, setSessions] = useState<Session[]>([]);
const [loadingHistory, setLoadingHistory] = useState(false);
```

**새 대화:**
- `setSessionId(null)`, `setMessages([])`, `setSessions` 갱신은 `/chat` 응답 후

**세션 전환 (`onSelect`):**
```
GET /sessions/{id}/messages
  → setMessages(history)
  → setSessionId(id)
```
실패 시 전환 취소, 기존 상태 유지.

**세션 삭제 (`onDelete`):**
```
Optimistic: setSessions(prev => prev.filter(...))
DELETE /sessions/{id}
  실패 시 → GET /sessions 재호출로 롤백
  삭제된 세션이 active → setSessionId(null), setMessages([])
```

**세션 목록 갱신:** `/chat` 직전 `sessionId === null`이었던 경우(신규 세션 생성)에만 `GET /sessions` 재호출. 기존 세션 계속 대화 시에는 목록이 변하지 않으므로 재조회 불필요.

---

## 4. 데이터 흐름

```
[첫 질문]
  POST /chat (session_id: null)
  → 백엔드: create_session + add_message ×2
  ← { answer, sources, session_id }
  → 프론트: setSessionId, setMessages 추가, GET /sessions

[세션 전환]
  GET /sessions/{id}/messages
  ← [{ role, content, sources }]
  → setMessages(history), setSessionId(id)

[세션 삭제]
  Optimistic remove → DELETE /sessions/{id}
  실패 시 GET /sessions 재호출로 롤백
```

---

## 5. 에러 처리

| 상황 | 처리 |
|------|------|
| `GET /sessions` 실패 | 사이드바에 "목록을 불러올 수 없습니다" 표시. 채팅 정상 동작. |
| `GET /sessions/{id}/messages` 실패 | 세션 전환 취소, 기존 세션 유지, 기존 에러 표시 패턴 재사용 |
| `DELETE /sessions/{id}` 실패 | Optimistic 제거 롤백 (`GET /sessions` 재호출) |
| `add_message` 실패 (백엔드) | 채팅 응답은 이미 반환됨 — 로그 기록만, 사용자에게 에러 미노출 |

---

## 6. 테스트

| 대상 | 종류 | 내용 |
|------|------|------|
| `InMemorySessionStore` | 단위 | CRUD 전체 동작, 타 유저 세션 격리 |
| `app/api/sessions.py` | 통합 | `TestClient` + JWT 인증 포함, 타 유저 접근 차단 확인 |
| `SessionSidebar` | 단위 | 렌더링, 세션 클릭, 삭제 클릭 이벤트 |
| eval runner | 회귀 | recall@5 점수 변동 없어야 함 (세션 로직은 RAG 품질에 무관) |

---

## 7. 범위 외 (이번 구현 제외)

- 세션 제목 수동 편집
- 세션 검색
- 세션 핀 고정
- 모바일 반응형 (사이드바 드로어)
- PostgresSessionStore 구현 (prod 배포 시점에 추가)

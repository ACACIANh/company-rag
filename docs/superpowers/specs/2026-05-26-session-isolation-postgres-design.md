# 세션 히스토리 격리 및 PostgreSQL 마이그레이션 설계

## 목표

1. 사용자 간 세션 히스토리 격리 — 현재 `thread_id`(UUID)만으로 MemorySaver를 조회해 타 사용자 대화 맥락에 접근 가능한 구조 수정
2. `InMemorySessionStore` → `PostgresSessionStore` — 서버 재시작 후 세션 목록·메시지 소멸 문제 해결

## 범위 외

- LangGraph `MemorySaver` PostgreSQL 마이그레이션: 인터페이스 교체 비용이 1줄이므로 스케일아웃 또는 맥락 영속 요구 시점에 별도 태스크로 처리

## 설계

### 1. thread_id 네임스페이스

**문제**: `/chat`이 클라이언트가 넘긴 `session_id`를 그대로 MemorySaver 키로 사용. 사용자 A가 사용자 B의 `session_id`를 알면 B의 AgentState를 로드할 수 있음.

**해결**: MemorySaver 내부 키를 `{user_id}:{session_id}`로 구성. 클라이언트 인터페이스(session_id)는 변경 없음.

```
클라이언트 → session_id: "550e8400"
서버 내부  → thread_id: "alice:550e8400"   (MemorySaver 키)
SessionStore → thread_id: "550e8400"        (사용자 식별용 원본 유지)
```

변경 위치: `app/api/chat.py` — `thread_id` 구성 로직 1곳.

### 2. /chat 소유권 검증

기존 `session_id`가 요청으로 들어올 때 SessionStore에서 소유권 확인. 미소유 시 403 반환.

```python
if req.session_id:
    owned = {s.thread_id for s in store.list_sessions(current_user["user_id"])}
    if req.session_id not in owned:
        raise HTTPException(status_code=403, detail="Session not found")
```

네임스페이스(구조적 방어) + 소유권 검증(API 레이어 방어) 두 겹.

### 3. PostgresSessionStore

`shared/session/adapters/postgres.py` 신규 작성. 기존 `PostgresCacheBackend`와 동일한 `psycopg2` connection pool 패턴 적용.

**스키마**:

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    thread_id   TEXT        PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL   PRIMARY KEY,
    thread_id   TEXT        NOT NULL REFERENCES chat_sessions(thread_id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    sources     JSONB       NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, created_at);
```

**메서드 구현**:

- `create_session`: `INSERT ... ON CONFLICT DO NOTHING` (멱등)
- `list_sessions`: `user_id` 필터 + `created_at DESC` 정렬
- `get_messages`: `thread_id` 필터 + `created_at ASC` 정렬
- `add_message`: `INSERT`. 존재하지 않는 `thread_id` 시 `ForeignKeyViolation` 예외를 catch해 조용히 noop 처리 (InMemorySessionStore 동작과 동일)
- `delete_session`: `DELETE` where `thread_id = %s AND user_id = %s`

### 4. factory.py 업데이트

`SESSION_STORE_TYPE=postgres` + `POSTGRES_DSN` 설정 시 `PostgresSessionStore` 반환.

## 영향 범위

| 파일 | 변경 |
|---|---|
| `shared/session/adapters/postgres.py` | 신규 |
| `shared/session/factory.py` | `NotImplementedError` → 실제 분기 |
| `app/api/chat.py` | thread_id 네임스페이스 + 소유권 검증 |
| `tests/shared/test_session_store.py` | `PostgresSessionStore` 테스트 추가 (pytest-mock으로 DB 격리) |
| `tests/app/api/test_chat.py` | thread_id 네임스페이스 반영 수정 |

## 환경변수

기존 변수 재활용, 신규 추가 없음:

- `SESSION_STORE_TYPE=postgres` (기본값: `memory`)
- `POSTGRES_DSN=postgresql://user:pass@host/db`

## 테스트 전략

- `PostgresSessionStore` 단위 테스트: `psycopg2.connect`를 Mock으로 교체해 실제 DB 없이 SQL 호출 검증
- `/chat` 소유권 검증: 기존 `test_chat.py`에 403 케이스 추가
- `test_chat_uses_provided_session_id`: thread_id 네임스페이스 반영 (`{user_id}:{session_id}` 형태로 assertion 수정)

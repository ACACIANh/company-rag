# PostgreSQL 체크포인터 & 세션 스토어 이관 설계

## 배경

서버 재시작 시 세션이 소멸되는 문제. 두 컴포넌트가 모두 인-메모리 저장소를 사용 중:

- **LangGraph 체크포인터**: `MemorySaver()` — 그래프 상태(HITL interrupt 포함) 서버 재시작 시 소멸
- **SessionStore**: `InMemorySessionStore` (기본값) — 채팅 히스토리 서버 재시작 시 소멸

## 목표

서버 재시작 후에도 세션 컨텍스트(채팅 히스토리, HITL 상태) 유지.

## 결정: 공식 패키지 사용

`langgraph-checkpoint-postgres` (`AsyncPostgresSaver`) 사용.
- LangGraph 공식 지원, 검증된 스키마 관리
- psycopg3 드라이버 추가되나, 역할이 분리되어 충돌 없음
  - `asyncpg`: 앱 쿼리 (FGA 캐시, 세션, 벡터 스토어)
  - `psycopg3`: LangGraph 체크포인트 전용

## 변경 범위

### 1. `requirements.txt`
```
langgraph-checkpoint-postgres
psycopg[binary,pool]
```

### 2. `app/graph/builder.py`
- `build_graph()` 시그니처에 `checkpointer` 파라미터 추가
- 내부 `MemorySaver()` 생성 제거
- `MemorySaver` import 제거

### 3. `app/api/chat.py`
- lifespan에서 `AsyncPostgresSaver.from_conn_string(config.postgres_dsn)` 생성
- `await checkpointer.setup()` 호출 (테이블 자동 생성)
- `build_graph(checkpointer=checkpointer)` 주입
- `AsyncPostgresSaver`는 async context manager — lifespan의 `yield` 범위 안에서 열고 닫음

### 4. `.env` / `.env.example`
```
SESSION_STORE_TYPE=postgres
```
`POSTGRES_DSN`은 기존에 설정되어 있으므로 추가 환경변수 불필요.

## 데이터 흐름

```
채팅 요청
  → SessionStore (chat_sessions / chat_messages) — asyncpg
  → LangGraph graph.ainvoke()
      → checkpointer (langgraph_checkpoints 등) — psycopg3
```

## 테스트 영향

- `test_builder.py`: `build_graph()` 호출 시 `MemorySaver()`를 직접 전달하면 되므로 변경 없음
- 기존 세션 관련 테스트: `PostgresSessionStore` 또는 `InMemorySessionStore` 선택 가능 — 변경 없음

## 완료 기준

1. 서버 재시작 후 기존 `session_id`로 채팅 히스토리 유지
2. HITL interrupt 대기 중 재시작 후 상태 복구 (thread_id 동일 시)
3. 기존 단위 테스트 통과

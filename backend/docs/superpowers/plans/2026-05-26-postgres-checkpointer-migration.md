# PostgreSQL 체크포인터 & 세션 스토어 이관 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서버 재시작 후에도 세션 컨텍스트(채팅 히스토리, HITL 상태)가 유지되도록 인-메모리 저장소를 PostgreSQL로 이관한다.

**Architecture:** SessionStore는 이미 `PostgresSessionStore`가 구현되어 있어 환경변수만 변경하면 된다. LangGraph 체크포인터는 `MemorySaver` → `AsyncPostgresSaver`(공식 패키지)로 교체하고, lifespan에서 생성·주입하는 방식으로 변경한다.

**Tech Stack:** `langgraph-checkpoint-postgres`, `psycopg[binary,pool]`, 기존 `asyncpg` pool (SessionStore용)

---

## 변경 파일 목록

| 파일 | 역할 |
|------|------|
| `requirements.txt` | 패키지 추가 |
| `app/graph/builder.py` | `build_graph()` checkpointer 파라미터 추가 |
| `app/api/chat.py` | lifespan에서 `AsyncPostgresSaver` 생성·주입 |
| `.env` | `SESSION_STORE_TYPE=postgres` 추가 |
| `.env.example` | 동일 |

테스트 파일 변경 없음 — `build_graph()` 호출 시 `checkpointer` 미전달 시 `MemorySaver()` 사용(기본값).

---

### Task 1: 패키지 설치

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt에 의존성 추가**

`requirements.txt`의 `langgraph>=0.2.0` 줄 다음에 두 줄을 추가한다:

```
langgraph>=0.2.0
langgraph-checkpoint-postgres>=2.0.0
psycopg[binary,pool]>=3.1.0
```

- [ ] **Step 2: 패키지 설치**

```bash
.venv/bin/pip install langgraph-checkpoint-postgres "psycopg[binary,pool]"
```

Expected: 설치 완료 메시지, 에러 없음.

- [ ] **Step 3: 설치 확인**

```bash
.venv/bin/pip show langgraph-checkpoint-postgres psycopg
```

Expected: `Name: langgraph-checkpoint-postgres` 및 `Name: psycopg` 출력.

- [ ] **Step 4: 커밋**

```bash
git add requirements.txt
git commit -m "chore: add langgraph-checkpoint-postgres and psycopg deps"
```

---

### Task 2: `build_graph()` checkpointer 파라미터 추가

**Files:**
- Modify: `app/graph/builder.py`

- [ ] **Step 1: 기존 테스트가 통과하는지 먼저 확인**

```bash
.venv/bin/pytest tests/app/graph/test_builder.py -v --tb=short
```

Expected: 모든 테스트 PASS (변경 전 베이스라인).

- [ ] **Step 2: `build_graph()` 시그니처에 `checkpointer` 파라미터 추가**

`app/graph/builder.py`의 `build_graph` 함수 시그니처를 아래와 같이 수정한다.

변경 전:
```python
def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
    reranker: Reranker | None = None,
    fga_client: FGAClient | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
) -> CompiledStateGraph:
```

변경 후:
```python
def build_graph(
    retriever: Retriever,
    llm: LLMClient,
    web_search_retriever: Retriever | None = None,
    reranker: Reranker | None = None,
    fga_client: FGAClient | None = None,
    retrieve_top_k: int = 20,
    top_k: int = 5,
    checkpointer=None,
) -> CompiledStateGraph:
```

- [ ] **Step 3: 함수 마지막 줄을 checkpointer 주입 방식으로 변경**

변경 전 (`builder.py` 마지막 줄):
```python
    return g.compile(checkpointer=MemorySaver())
```

변경 후:
```python
    if checkpointer is None:
        checkpointer = MemorySaver()
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: `MemorySaver` import는 유지 (테스트·기본값에서 사용)**

`from langgraph.checkpoint.memory import MemorySaver` import는 그대로 둔다. 제거하지 않는다.

- [ ] **Step 5: 기존 테스트 재실행**

```bash
.venv/bin/pytest tests/app/graph/test_builder.py -v --tb=short
```

Expected: 모든 테스트 PASS. `build_graph()` 인자 없이 호출 시 `MemorySaver()`가 기본으로 사용됨.

- [ ] **Step 6: 커밋**

```bash
git add app/graph/builder.py
git commit -m "feat: build_graph accepts external checkpointer, defaults to MemorySaver"
```

---

### Task 3: lifespan에서 `AsyncPostgresSaver` 생성·주입

**Files:**
- Modify: `app/api/chat.py`

- [ ] **Step 1: import 추가**

`app/api/chat.py` 상단 import 블록에 추가:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
```

- [ ] **Step 2: lifespan 함수에서 `AsyncPostgresSaver` 생성 및 setup**

현재 lifespan의 `graph = build_graph(...)` 부분을 아래와 같이 교체한다.

변경 전:
```python
    graph = build_graph(
        retriever=retriever, llm=llm, reranker=reranker, fga_client=fga_client
    )

    app.state.pool = pool
    app.state.store = store
    app.state.fga_client = fga_client
    app.state.session_store = session_store
    app.state.graph = graph

    yield

    await pool.close()
```

변경 후:
```python
    async with AsyncPostgresSaver.from_conn_string(config.postgres_dsn) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(
            retriever=retriever, llm=llm, reranker=reranker, fga_client=fga_client,
            checkpointer=checkpointer,
        )

        app.state.pool = pool
        app.state.store = store
        app.state.fga_client = fga_client
        app.state.session_store = session_store
        app.state.graph = graph

        yield

        await pool.close()
```

- [ ] **Step 3: 서버 기동 테스트**

```bash
.venv/bin/uvicorn app.api.chat:app --reload --port 8000
```

Expected: `Application startup complete.` 출력, 에러 없음.
PostgreSQL 연결 실패 시 `POSTGRES_DSN` 환경변수를 확인한다.

- [ ] **Step 4: 커밋**

```bash
git add app/api/chat.py
git commit -m "feat: wire AsyncPostgresSaver as LangGraph checkpointer in lifespan"
```

---

### Task 4: 환경변수 설정 — SESSION_STORE_TYPE=postgres

**Files:**
- Modify: `.env`
- Modify: `.env.example`

- [ ] **Step 1: `.env`에 SESSION_STORE_TYPE 추가**

`.env` 파일의 `POSTGRES_DSN=...` 줄 바로 다음에 추가:

```
SESSION_STORE_TYPE=postgres
```

- [ ] **Step 2: `.env.example`에도 추가**

`.env.example`의 `# PostgreSQL` 섹션 아래에 추가:

```
SESSION_STORE_TYPE=postgres
```

- [ ] **Step 3: 서버 재기동 후 세션 스토어 확인**

서버를 재시작하고 로그에서 `PostgresSessionStore`가 사용되는지 확인:

```bash
.venv/bin/uvicorn app.api.chat:app --port 8000
```

또는 Python으로 직접 확인:
```python
import os
os.environ["SESSION_STORE_TYPE"] = "postgres"
os.environ["POSTGRES_DSN"] = "postgresql://fga:fga@localhost:5432/app"
from shared.config import load_config
from shared.session.factory import create_session_store
import asyncpg, asyncio

async def check():
    pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"])
    store = create_session_store(load_config(), pool)
    print(type(store).__name__)  # PostgresSessionStore 출력 확인
    await pool.close()

asyncio.run(check())
```

Expected: `PostgresSessionStore`

- [ ] **Step 4: 커밋**

```bash
git add .env.example
git commit -m "feat: set SESSION_STORE_TYPE=postgres as default"
```

> `.env`는 `.gitignore`에 포함되어 있으므로 커밋에서 제외한다.

---

### Task 5: 통합 검증

- [ ] **Step 1: 전체 테스트 실행**

```bash
.venv/bin/pytest tests/ -v --tb=short --ignore=tests/eval
```

Expected: 모든 테스트 PASS.

- [ ] **Step 2: 서버 재시작 후 세션 유지 수동 확인**

1. 서버 시작: `.venv/bin/uvicorn app.api.chat:app --port 8000`
2. 로그인 후 `/chat` 또는 `/chat/stream`으로 대화 1회 진행 — `session_id` 기록
3. 서버 종료 후 재시작
4. 동일 `session_id`로 후속 질문 전송
5. Expected: 이전 대화 히스토리가 `chat_history`에 포함된 채 응답

- [ ] **Step 3: PostgreSQL 테이블 확인**

```bash
psql postgresql://fga:fga@localhost:5432/app -c "\dt"
```

Expected: `chat_sessions`, `chat_messages`, `checkpoints`, `checkpoint_blobs`, `checkpoint_migrations` 테이블 존재.

- [ ] **Step 4: 최종 커밋 (필요 시)**

```bash
git add .
git commit -m "chore: postgres migration complete — session and checkpointer"
```

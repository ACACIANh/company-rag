# business 스키마 쓰기 허용(UPDATE/DELETE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 게이트 통제 하에 business 스키마에 UPDATE/DELETE를 허용하되, 이중 계정/풀 + WHERE 가드로 방어심층을 보존한다.

**Architecture:** SELECT는 기존 read-only 계정(`sql_tool_ro`), 게이트가 `update_delete`로 통과시킨 쓰기만 신규 쓰기 계정(`sql_tool_rw`)으로 실행한다. WHERE 없는 무조건 UPDATE/DELETE와 INSERT/MERGE는 sqlglot AST 단계에서 DENY로 닫는다. 도구 description을 정정해 변경 요청이 권한 도구로 오라우팅되지 않게 한다.

**Tech Stack:** Python 3.11+, asyncpg, sqlglot, LangGraph, pytest.

작업 디렉토리는 항상 `backend/`. 테스트는 `.venv/bin/python -m pytest`. 브랜치는 이미 `feat/business-write-gate`.

---

### Task 1: risk.py — WHERE 가드 + INSERT/MERGE 차단

**Files:**
- Modify: `core/sql/risk.py:28-43`
- Test: `tests/core/sql/test_risk.py`

기존 `_classify_statement`는 INSERT/UPDATE/DELETE/MERGE를 모두 `RISK_UPDATE_DELETE`로 분류한다. spec 범위(UPDATE/DELETE만, WHERE 필수)에 맞게 세분화한다.

- [ ] **Step 1: 실패 테스트 추가**

`tests/core/sql/test_risk.py`에 기존 테스트가 있으면 그 파일 끝에 추가, 없으면 파일을 만들고 상단에 `from core.sql.risk import classify_sql_ast, RISK_UPDATE_DELETE, RISK_DENY, RISK_SELECT`를 둔다.

```python
def test_update_with_where_is_update_delete():
    assert classify_sql_ast("UPDATE business.employees SET salary = 1 WHERE emp_id = 'x'") == RISK_UPDATE_DELETE

def test_delete_with_where_is_update_delete():
    assert classify_sql_ast("DELETE FROM business.employees WHERE emp_id = 'x'") == RISK_UPDATE_DELETE

def test_update_without_where_is_deny():
    assert classify_sql_ast("UPDATE business.employees SET salary = 0") == RISK_DENY

def test_delete_without_where_is_deny():
    assert classify_sql_ast("DELETE FROM business.employees") == RISK_DENY

def test_insert_is_deny():
    assert classify_sql_ast("INSERT INTO business.employees (emp_id) VALUES ('x')") == RISK_DENY

def test_plain_select_unaffected():
    assert classify_sql_ast("SELECT salary FROM business.employees WHERE emp_id = 'x'") == RISK_SELECT
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/sql/test_risk.py -k "without_where or insert_is_deny" -q`
Expected: FAIL (현재 INSERT·WHERE없음이 update_delete로 분류됨)

- [ ] **Step 3: 구현**

`core/sql/risk.py`의 `_WRITE_TYPES`(line 29) 정의를 삭제하고, `_classify_statement`(line 32-43)를 아래로 교체한다. `_DDL_TYPES`(line 28)는 유지한다.

```python
def _classify_statement(stmt: exp.Expression) -> str:
    # sqlglot이 구조화하지 못한 raw 구문(Command, 예: VACUUM)은 미지원 → DENY
    if isinstance(stmt, exp.Command) or list(stmt.find_all(exp.Command)):
        return RISK_DENY
    # DDL은 별도 최상위 등급
    if list(stmt.find_all(*_DDL_TYPES)):
        return RISK_DDL
    # INSERT·MERGE는 본 게이트 범위 밖(쓰기 허용은 UPDATE/DELETE 한정) → DENY
    if list(stmt.find_all(exp.Insert, exp.Merge)):
        return RISK_DENY
    # UPDATE/DELETE: WHERE 절이 없는 무조건 변경(전체 레코드 영향)은 차단
    writes = list(stmt.find_all(exp.Update, exp.Delete))
    if writes:
        if any(w.args.get("where") is None for w in writes):
            return RISK_DENY
        return RISK_UPDATE_DELETE
    if isinstance(stmt, exp.Select) or list(stmt.find_all(exp.Select)):
        return RISK_SELECT
    return RISK_DENY
```

- [ ] **Step 4: 통과 확인 (회귀 포함)**

Run: `.venv/bin/python -m pytest tests/core/sql/test_risk.py -q`
Expected: PASS (전부)

- [ ] **Step 5: 커밋**

```bash
git add core/sql/risk.py tests/core/sql/test_risk.py
git commit -m "feat(risk): WHERE 없는 UPDATE/DELETE·INSERT를 DENY로 차단"
```

---

### Task 2: execute 인터페이스를 (planned_action, risk)로 통일

**Files:**
- Modify: `app/graph/tools/base.py:18-20`
- Modify: `app/graph/tools/sql_tool.py:58-64`
- Modify: `app/graph/tools/permission_tool.py:57`
- Modify: `app/graph/nodes/tool_gate.py:59`
- Modify: `app/graph/nodes/justify_execute.py:21`

이 단계는 시그니처만 통일한다(rw 풀 분기는 Task 4). `risk`를 받되 동작은 기존과 동일하게 유지해 기존 테스트가 그대로 통과해야 한다.

- [ ] **Step 1: base.py 프로토콜 갱신**

`app/graph/tools/base.py`의 `execute`(line 18-20)를 교체:

```python
    async def execute(self, planned_action: str, risk: str) -> str:
        """구체화된 동작 실행 → 결과 텍스트. risk는 실행 경로(읽기/쓰기) 선택에 쓴다."""
        ...
```

- [ ] **Step 2: sql_tool.py execute 시그니처 변경**

`app/graph/tools/sql_tool.py`의 `execute`(line 58)를 `async def execute(self, planned_action: str, risk: str) -> str:`로 바꾼다. 본문은 이 단계에서 변경하지 않는다(`risk` 미사용 — Task 4에서 분기 추가).

- [ ] **Step 3: permission_tool.py execute 시그니처 변경**

`app/graph/tools/permission_tool.py`의 `execute`(line 57)를 `async def execute(self, planned_action: str, risk: str) -> str:`로 바꾼다. 본문 변경 없음(권한 도구는 풀 분기가 없어 `risk` 미사용 — 시그니처 일치 목적).

- [ ] **Step 4: 호출부 갱신**

`app/graph/nodes/tool_gate.py:59` `result = await handler.execute(planned_action)` → `result = await handler.execute(planned_action, risk)` (같은 루프의 `risk` 변수 사용).

`app/graph/nodes/justify_execute.py:21` `result = await handler.execute(p["planned_action"])` → `result = await handler.execute(p["planned_action"], p["risk"])`.

- [ ] **Step 5: 회귀 확인**

Run: `.venv/bin/python -m pytest tests/app/graph -q`
Expected: PASS (시그니처만 바뀌고 동작 동일하므로 기존 테스트 전부 통과)

- [ ] **Step 6: 커밋**

```bash
git add app/graph/tools/base.py app/graph/tools/sql_tool.py app/graph/tools/permission_tool.py app/graph/nodes/tool_gate.py app/graph/nodes/justify_execute.py
git commit -m "refactor(tools): execute 인터페이스를 (planned_action, risk)로 통일"
```

---

### Task 3: DB 쓰기 계정 `sql_tool_rw` + config + .env

**Files:**
- Modify: `scripts/seed_business.py:1-10, 99-160`
- Modify: `core/config.py:45, 72`
- Modify: `.env`
- Test: `tests/scripts/test_seed_business.py`

- [ ] **Step 1: grant SQL 테스트 추가**

`tests/scripts/test_seed_business.py`에 추가. 함수명은 Task 3에서 새로 만들 `_grant_rw_sql`를 검증한다.

```python
def test_grant_rw_sql_grants_select_update_delete_only():
    from scripts.seed_business import _grant_rw_sql
    sql = _grant_rw_sql("pw")
    assert "GRANT SELECT, UPDATE, DELETE ON ALL TABLES IN SCHEMA business TO sql_tool_rw" in sql
    assert "INSERT" not in sql            # INSERT 미부여
    assert "REVOKE ALL ON SCHEMA public FROM sql_tool_rw" in sql   # 운영 스키마 차단
    assert "default_transaction_read_only = on" not in sql         # 쓰기 계정은 RO 트랜잭션 아님
    assert "statement_timeout" in sql                              # timeout 방어는 유지
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_business.py::test_grant_rw_sql_grants_select_update_delete_only -q`
Expected: FAIL (`_grant_rw_sql` 없음)

- [ ] **Step 3: seed_business.py에 `_grant_rw_sql` 추가**

`scripts/seed_business.py`의 `_grant_sql`(line 99-125) 바로 아래에 추가:

```python
def _grant_rw_sql(password: str) -> str:
    """쓰기 제한계정 생성 + 권한 (멱등). business 스키마 SELECT/UPDATE/DELETE만,
    INSERT·DDL·public 스키마는 미부여(ADR-0034 방어심층 2차)."""
    pw = password.replace("'", "''")
    return f"""
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sql_tool_rw') THEN
      CREATE ROLE sql_tool_rw LOGIN PASSWORD '{pw}';
   ELSE
      ALTER ROLE sql_tool_rw LOGIN PASSWORD '{pw}';
   END IF;
END
$$;

-- 운영 객체(public 스키마) 접근 차단
REVOKE ALL ON SCHEMA public FROM sql_tool_rw;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM sql_tool_rw;

-- business 스키마: 읽기 + UPDATE/DELETE만 (INSERT·DDL 미부여)
GRANT USAGE ON SCHEMA business TO sql_tool_rw;
GRANT SELECT, UPDATE, DELETE ON ALL TABLES IN SCHEMA business TO sql_tool_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA business GRANT SELECT, UPDATE, DELETE ON TABLES TO sql_tool_rw;

-- 계정 레벨 방어: statement timeout (쓰기 계정이라 RO 트랜잭션은 설정하지 않음)
ALTER ROLE sql_tool_rw SET statement_timeout = '5s';
"""
```

- [ ] **Step 4: main()에서 rw 계정 grant 실행**

`scripts/seed_business.py`의 `main()`에서 password 로드부(line 130) 아래에 추가:

```python
    rw_password = os.getenv("SQL_TOOL_RW_PASSWORD", "sql_tool_rw_dev")
```

그리고 `await conn.execute(_grant_sql(password))`(line 153) 바로 아래에 추가:

```python
        await conn.execute(_grant_rw_sql(rw_password))
```

완료 메시지(line 157-160)의 끝 문자열을 `"제한계정 sql_tool_ro(read-only)·sql_tool_rw(SELECT/UPDATE/DELETE)"`로 바꾸고, docstring(line 6, 9)에 rw 계정·`SQL_TOOL_RW_PASSWORD`를 한 줄 추가한다.

- [ ] **Step 5: config.py 확장**

`core/config.py`의 `Config` 데이터클래스(line 45) `sql_tool_dsn: str` 아래에 `sql_tool_rw_dsn: str` 추가. `load_config()`(line 72) `sql_tool_dsn=...` 아래에 `sql_tool_rw_dsn=os.getenv("SQL_TOOL_RW_DSN", ""),` 추가.

- [ ] **Step 6: .env 추가**

`.env`의 `SQL_TOOL_DSN=` 줄 아래에 추가:

```
SQL_TOOL_RW_DSN=postgresql://sql_tool_rw:sql_tool_rw_dev@localhost:5432/app
```

- [ ] **Step 7: 테스트 + 실제 시드 적용**

Run: `.venv/bin/python -m pytest tests/scripts/test_seed_business.py -q`
Expected: PASS

Run: `.venv/bin/python -m scripts.seed_business`
Expected: "business 시드 완료 ... sql_tool_rw(SELECT/UPDATE/DELETE)" 출력

검증: `docker compose exec -T postgres psql -U sql_tool_rw -d app -c "select count(*) from business.employees;"` 가 동작하고(SELECT), `psql -U sql_tool_rw -d app -c "insert into business.employees (emp_id,name,department,position,hire_date,salary,email) values ('z','z','z','z','2020-01-01',1,'z');"` 가 권한 거부되어야 한다.

- [ ] **Step 8: 커밋**

```bash
git add scripts/seed_business.py core/config.py tests/scripts/test_seed_business.py .env
git commit -m "feat(db): business 쓰기 제한계정 sql_tool_rw 추가(SELECT/UPDATE/DELETE)"
```

---

### Task 4: SqlToolHandler 이중 풀 + 쓰기 실행 + 배선

**Files:**
- Modify: `app/graph/tools/sql_tool.py:23-64`
- Modify: `app/graph/tools/registry.py:22-29`
- Modify: `app/graph/builder.py:58, 65`
- Modify: `app/api/chat.py:77, 93, 104-105`
- Test: `tests/app/graph/tools/test_sql_tool.py`

- [ ] **Step 1: 핸들러 풀 분기 테스트 추가**

`tests/app/graph/tools/test_sql_tool.py`(없으면 생성). 상단:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.graph.tools.sql_tool import SqlToolHandler
from core.sql.risk import RISK_SELECT, RISK_UPDATE_DELETE


def _pool(fetch_return=None, execute_return="UPDATE 2"):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_return or [{"salary": 100}])
    conn.execute = AsyncMock(return_value=execute_return)
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=None)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=None)))
    return pool, conn


@pytest.mark.asyncio
async def test_select_uses_ro_pool():
    ro, ro_conn = _pool()
    rw, rw_conn = _pool()
    h = SqlToolHandler(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)
    await h.execute("SELECT salary FROM business.employees WHERE emp_id='x'", RISK_SELECT)
    ro_conn.fetch.assert_awaited_once()
    rw_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_uses_rw_pool_and_reports_rows():
    ro, ro_conn = _pool()
    rw, rw_conn = _pool(execute_return="UPDATE 3")
    h = SqlToolHandler(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)
    result = await h.execute("UPDATE business.employees SET salary=1 WHERE emp_id='x'", RISK_UPDATE_DELETE)
    rw_conn.execute.assert_awaited_once()
    ro_conn.fetch.assert_not_awaited()
    assert "3" in result


@pytest.mark.asyncio
async def test_update_without_rw_pool_errors():
    ro, _ = _pool()
    h = SqlToolHandler(llm=MagicMock(), sql_pool=ro, sql_rw_pool=None)
    result = await h.execute("UPDATE business.employees SET salary=1 WHERE emp_id='x'", RISK_UPDATE_DELETE)
    assert "오류" in result
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -q`
Expected: FAIL (`sql_rw_pool` 인자 없음)

- [ ] **Step 3: SqlToolHandler 구현**

`app/graph/tools/sql_tool.py`의 import에 `RISK_UPDATE_DELETE` 추가(line 10 수정):

```python
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, classify_sql_ast
```

`_format_rows`(line 24) 아래에 헬퍼 추가:

```python
def _affected_rows(status: str) -> str:
    """asyncpg execute status('UPDATE 3'/'DELETE 2')에서 영향 행 수 추출."""
    parts = status.split()
    return parts[-1] if parts and parts[-1].isdigit() else "0"
```

`__init__`(line 37-45)에 `sql_rw_pool` 인자 추가:

```python
    def __init__(self, *, llm: LLMClient, sql_pool: asyncpg.Pool, sql_rw_pool: asyncpg.Pool = None, row_limit: int = _DEFAULT_ROW_LIMIT) -> None:
        self._llm = llm
        self._pool = sql_pool
        self._rw_pool = sql_rw_pool
        self._row_limit = row_limit
        self.tool = Tool(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda question: "",
        )
```

`execute`(Task 2에서 시그니처만 바뀐 상태, line 58)를 교체:

```python
    async def execute(self, planned_action: str, risk: str) -> str:
        if risk == RISK_UPDATE_DELETE:
            if self._rw_pool is None:
                return "SQL 실행 오류: 쓰기 풀 미구성"
            try:
                async with self._rw_pool.acquire() as conn:
                    async with conn.transaction():
                        status = await conn.execute(planned_action)
                return f"{_affected_rows(status)}개 행이 변경되었습니다."
            except Exception as exc:
                return f"SQL 실행 오류: {type(exc).__name__}"
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(planned_action)
            return _format_rows(list(rows)[:self._row_limit])
        except Exception as exc:
            return f"SQL 실행 오류: {type(exc).__name__}"
```

- [ ] **Step 4: 핸들러 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -q`
Expected: PASS

- [ ] **Step 5: registry 배선**

`app/graph/tools/registry.py:22` 시그니처를 `def build_tool_registry(*, llm: LLMClient, sql_pool, sql_rw_pool=None, fga_client: FGAClient) -> ToolRegistry:`로, line 23을 `sql = SqlToolHandler(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool)`로.

- [ ] **Step 6: builder 배선**

`app/graph/builder.py:58` `sql_pool: Any = None,` 아래에 `sql_rw_pool: Any = None,` 추가. line 65 `registry = build_tool_registry(llm=llm, sql_pool=sql_pool, fga_client=fga_client)`를 `registry = build_tool_registry(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool, fga_client=fga_client)`로.

- [ ] **Step 7: lifespan 배선**

`app/api/chat.py:77` 아래에 추가:

```python
    sql_rw_pool = await asyncpg.create_pool(config.sql_tool_rw_dsn) if config.sql_tool_rw_dsn else None
```

line 91-94 `build_graph(...)` 호출에 `sql_rw_pool=sql_rw_pool,` 추가. line 104-105 정리부에 추가:

```python
        if sql_rw_pool is not None:
            await sql_rw_pool.close()
```

- [ ] **Step 8: 회귀 확인**

Run: `.venv/bin/python -m pytest tests/app -q`
Expected: PASS (전부)

- [ ] **Step 9: 커밋**

```bash
git add app/graph/tools/sql_tool.py app/graph/tools/registry.py app/graph/builder.py app/api/chat.py tests/app/graph/tools/test_sql_tool.py
git commit -m "feat(sql-tool): update_delete는 쓰기 풀로 실행하고 영향 행수 반환"
```

---

### Task 5: 도구 description 정정 (오라우팅 해소)

**Files:**
- Modify: `app/graph/tools/sql_tool.py:17-21`
- Modify: `app/graph/tools/permission_tool.py:21-25`

- [ ] **Step 1: query_business_data description 정정**

`app/graph/tools/sql_tool.py`의 `_DESCRIPTION`(line 17-21)을 교체:

```python
_DESCRIPTION = (
    "사내 업무 DB(business.employees, business.sales)의 레코드를 조회·수정·삭제한다. "
    "직원/매출 값을 묻는 조회뿐 아니라 '연봉을 바꿔줘', '행을 삭제해줘' 같은 데이터 변경도 이 도구로 처리한다. "
    "권한 부여/회수가 아니라 '테이블 데이터' 작업일 때 쓴다. "
    "question 인자에 한국어 자연어 요청을 그대로 넣는다."
)
```

- [ ] **Step 2: manage_permission description 경계 명확화**

`app/graph/tools/permission_tool.py`의 `_DESCRIPTION`(line 21-25)을 교체:

```python
_DESCRIPTION = (
    "사내 접근 권한을 부여/회수한다(데이터 값 변경이 아님): 부서 멤버십, 폴더 부서 접근권, SQL 실행 권한 등급. "
    "예: '앨리스를 엔지니어링 부서에 추가', '세일즈 부서의 재무 폴더 열람권 회수'. "
    "직원 연봉·매출 같은 테이블 데이터 수정은 이 도구가 아니라 query_business_data를 쓴다. "
    "instruction 인자에 한국어 자연어 지시를 그대로 넣는다."
)
```

- [ ] **Step 3: 회귀 확인**

Run: `.venv/bin/python -m pytest tests/app/graph -q`
Expected: PASS (description은 문자열이라 기존 테스트 무영향)

- [ ] **Step 4: 커밋**

```bash
git add app/graph/tools/sql_tool.py app/graph/tools/permission_tool.py
git commit -m "fix(tools): SQL/권한 도구 description 경계 정정으로 변경 요청 오라우팅 해소"
```

---

### Task 6: e2e 통합 테스트 (게이트 → 쓰기 실행)

**Files:**
- Test: `tests/app/graph/test_builder.py` (끝에 추가)

기존 `test_builder.py`의 `_mock_chat_model`/`_tool_call_msg`/`_mock_fga_client`/`_make_initial_state` 헬퍼를 재사용한다. SQL 쓰기 풀은 별도 mock으로 주입한다.

- [ ] **Step 1: 통합 테스트 추가**

`tests/app/graph/test_builder.py` 끝에 추가:

```python
def _rw_pool(execute_return="UPDATE 1"):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=execute_return)
    conn.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=None)))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=None)))
    return pool


@pytest.mark.asyncio
async def test_engineering_update_justify_then_resume_writes():
    """engineering × WHERE 있는 UPDATE → JUSTIFY → 사유 resume → 쓰기 풀 실행 → 행수 답변."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "5번 직원 연봉 변경",                                                  # rewrite
        "agent",                                                          # router
        "UPDATE business.employees SET salary = 70000000 WHERE emp_id = 'user-5'",  # plan → SQL
    ]
    chat = _mock_chat_model([
        _tool_call_msg(question="연봉 변경"),                                  # 1차: 도구 호출 → interrupt
        AIMessage(content="1개 행을 변경했습니다."),                            # 2차: resume 후 최종 답변
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_update_delete"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), sql_rw_pool=_rw_pool("UPDATE 1"),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "eng-update-1"}}

    result = await graph.ainvoke(_make_initial_state("5번 직원 연봉 7000만으로 바꿔줘"), config=config)
    assert "__interrupt__" in result

    final = await graph.ainvoke(Command(resume="인사평가 반영 연봉 조정"), config=config)
    assert final["answer"] == "1개 행을 변경했습니다."


@pytest.mark.asyncio
async def test_general_update_denied_without_capability():
    """무소속(general) × UPDATE → justify_update_delete 미보유 → DENY, interrupt 없음."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "연봉 변경",                                                          # rewrite
        "agent",                                                          # router
        "UPDATE business.employees SET salary = 0 WHERE emp_id = 'user-5'",  # plan → SQL
    ]
    chat = _mock_chat_model([
        _tool_call_msg(question="연봉 변경"),
        AIMessage(content="권한이 없어 실행할 수 없습니다."),
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["sales"]),   # justify_update_delete 미보유
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), sql_rw_pool=_rw_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "general-update-deny-1"}}
    final = await graph.ainvoke(_make_initial_state("연봉 0으로 바꿔"), config=config)
    assert "__interrupt__" not in final
    assert final["answer"] == "권한이 없어 실행할 수 없습니다."


@pytest.mark.asyncio
async def test_update_without_where_denied_even_for_engineering():
    """engineering이라도 WHERE 없는 UPDATE는 risk=deny → DENY, interrupt 없음."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "전체 연봉 변경",                                                      # rewrite
        "agent",                                                          # router
        "UPDATE business.employees SET salary = 0",                          # plan → WHERE 없음 → deny
    ]
    chat = _mock_chat_model([
        _tool_call_msg(question="전체 연봉 변경"),
        AIMessage(content="무조건 변경은 허용되지 않습니다."),
    ])
    graph = build_graph(
        retriever=_make_retriever(), llm=llm,
        fga_client=_mock_fga_client(departments=["engineering"], capabilities=["justify_update_delete"]),
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), sql_rw_pool=_rw_pool(),
        chat_model=chat,
    )
    config = {"configurable": {"thread_id": "no-where-deny-1"}}
    final = await graph.ainvoke(_make_initial_state("전체 직원 연봉 0으로"), config=config)
    assert "__interrupt__" not in final
    assert final["answer"] == "무조건 변경은 허용되지 않습니다."
```

- [ ] **Step 2: 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -k "update" -q`
Expected: PASS (3개 신규 테스트)

- [ ] **Step 3: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/app -q`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/app/graph/test_builder.py
git commit -m "test(e2e): engineering UPDATE 게이트→쓰기 실행 / DENY / WHERE가드 검증"
```

---

### Task 7: ADR-0034 + CLAUDE.md + 인덱스

**Files:**
- Create: `docs/superpowers/decisions/ADR-0034-business-write-gate.md`
- Modify: `CLAUDE.md` (FGA/게이트 줄)
- Regenerate: `docs/superpowers/decisions/README.md`

- [ ] **Step 1: ADR 작성**

`docs/superpowers/decisions/ADR-0034-business-write-gate.md` 생성. 템플릿(`_template.md`)을 따르되 제목 아래 `> **Status**: 🟢 적용완료` 한 줄. 핵심 내용: read-only(ADR-0020)를 이중 계정으로 진화 — 게이트(1차)+쓰기계정 분리(2차)+WHERE 가드(3차) 방어심층. 쓰기 범위 UPDATE/DELETE 한정(INSERT/DDL 제외). ADR-0020을 보강(폐기 아님)하고 그 "실행 격리" 다이어그램을 ro/rw 이원화로 갱신. 도구 description 오라우팅 수정도 기록.

- [ ] **Step 2: CLAUDE.md 갱신**

`CLAUDE.md`의 "핵심 아키텍처 결정" FGA 항목 부근에 SQL 게이트 쓰기 허용 한 줄 추가: `SQL 도구: 읽기=sql_tool_ro, 쓰기(UPDATE/DELETE)=sql_tool_rw 이중 계정. WHERE 필수. 상세: ADR-0034.`

- [ ] **Step 3: 인덱스 재생성**

Run: `.venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성(ADR-0034 포함)

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/decisions/ADR-0034-business-write-gate.md docs/superpowers/decisions/README.md CLAUDE.md
git commit -m "docs(adr): ADR-0034 게이트 통제 business 쓰기 허용 + 이중 계정 방어심층"
```

---

## 최종 검증

- [ ] `.venv/bin/python -m pytest tests/ -q` 전체 통과
- [ ] 수동: 백엔드 재시작 → 브라우저 새로고침 → alice로 "id user-5 직원 연봉을 7000만으로 바꿔줘"(WHERE 유도되는 표현) → JUSTIFY → 사유 입력 → "N개 행이 변경되었습니다" + DB 반영 확인
- [ ] PR 생성 (DoD 체크리스트: 단위테스트 / eval 생략 사유 / ADR-0034)

## Self-Review 결과 (작성자 확인)

- **Spec 커버리지**: 쓰기 범위(Task 1·3), 이중 계정(Task 3·4), WHERE 가드(Task 1), description(Task 5), ADR(Task 7), 테스트(Task 1·4·6) — 전부 매핑됨.
- **Placeholder**: 없음 (모든 코드 블록 실체 포함).
- **타입/시그니처 일관성**: `execute(planned_action, risk)`가 base/sql_tool/permission_tool/호출부(Task 2)에서 일치. `build_tool_registry`/`build_graph`/`SqlToolHandler`의 `sql_rw_pool` 인자명이 Task 4 전반에서 일치. `_grant_rw_sql`(Task 3) 함수명이 테스트와 일치.

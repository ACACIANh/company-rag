# Audit History Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `query_audit_history` 도구를 LangGraph ReAct 루프에 추가해 관리자가 자연어로 `gate_audit_log`를 조회할 수 있게 한다.

**Architecture:** 기존 `ToolHandler` 패턴을 따른다. `tool_gate_node`가 `__caller_id`(요청 유저 ID)를 `args`에 주입하고, `AuditHistoryToolHandler.plan()`이 이를 `params_json`에 포함시켜 `execute()`에 전달한다. `execute()`는 FGA admin role을 확인 후 `gate_audit_log`를 SELECT한다. 위험도는 `RISK_SELECT`를 재사용해 게이트가 자동 ALLOW한다.

**Tech Stack:** Python 3.11, asyncpg, LangChain `StructuredTool`, OpenFGA (`fga_client.user_roles`), pytest-asyncio

---

## 파일 구조

| 동작 | 경로 | 역할 |
|---|---|---|
| **신규** | `app/graph/tools/audit_history_tool.py` | `AuditHistoryToolHandler` — plan/execute 구현 |
| **신규** | `tests/app/graph/tools/test_audit_history_tool.py` | 핸들러 단위 테스트 |
| **수정** | `app/graph/nodes/tool_gate.py` | `__caller_id` 주입 (1줄) |
| **수정** | `tests/app/graph/nodes/test_tool_gate.py` | 주입 검증 테스트 추가 |
| **수정** | `app/graph/tools/registry.py` | 핸들러 등록, `app_pool` 파라미터 추가 |
| **수정** | `tests/app/graph/tools/test_registry.py` | `app_pool` 파라미터 테스트 갱신 |
| **수정** | `app/graph/builder.py` | `app_pool` 파라미터 추가, registry에 전달 |
| **수정** | `app/api/chat.py` | `build_graph(app_pool=pool)` 전달 |
| **수정** | `tests/app/graph/test_builder.py` | `app_pool=AsyncMock()` 기존 호출에 추가 |

---

### Task 1: `tool_gate_node`에 `__caller_id` 주입

**Files:**
- Modify: `app/graph/nodes/tool_gate.py`
- Test: `tests/app/graph/nodes/test_tool_gate.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/nodes/test_tool_gate.py` 파일 끝에 추가:

```python
@pytest.mark.asyncio
async def test_caller_id_injected_into_plan():
    """tool_gate_node가 handler.plan() 호출 시 __caller_id를 args에 주입한다."""
    handler = _handler("SELECT 1", "select", result="ok")
    state = {
        "user_id": "alice",
        "question": "q",
        "agent_messages": [_ai([{"name": "query_business_data", "args": {"question": "x"}, "id": "c1"}])],
    }
    await tool_gate_node(
        state, registry=_registry(handler),
        fga_client=_fga([], ["sales"], capabilities=["allow_select"]), audit_sink=AsyncMock(),
    )
    call_args = handler.plan.call_args[0][0]
    assert call_args["__caller_id"] == "alice"
```

- [ ] **Step 2: 실패 확인**

```
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py::test_caller_id_injected_into_plan -v
```

예상: `FAILED` — `AssertionError: assert '__caller_id' in {}`

- [ ] **Step 3: 구현 — tool_gate.py 수정**

`app/graph/nodes/tool_gate.py`의 `plan()` 호출 줄을 변경:

```python
# 변경 전
planned_action, risk = handler.plan(tc["args"])

# 변경 후
planned_action, risk = handler.plan({**tc["args"], "__caller_id": user_id})
```

- [ ] **Step 4: 테스트 통과 확인**

```
.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -v
```

예상: 모든 테스트 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app/graph/nodes/tool_gate.py tests/app/graph/nodes/test_tool_gate.py
git commit -m "feat(tool_gate): plan() 호출 시 __caller_id 주입"
```

---

### Task 2: `AuditHistoryToolHandler` 구현

**Files:**
- Create: `app/graph/tools/audit_history_tool.py`
- Create: `tests/app/graph/tools/test_audit_history_tool.py`

- [ ] **Step 1: 테스트 파일 작성**

`tests/app/graph/tools/test_audit_history_tool.py` 신규 생성:

```python
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.tools.audit_history_tool import AuditHistoryToolHandler
from core.sql.risk import RISK_DENY, RISK_SELECT


def _fga(roles):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    return fga


def _pool(rows=None):
    """asyncpg pool mock — acquire()가 async context manager를 반환."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])

    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool, conn


def _make(roles=(), rows=None):
    fga = _fga(list(roles))
    pool, conn = _pool(rows)
    return AuditHistoryToolHandler(fga_client=fga, app_pool=pool), conn


# ── plan() 테스트 ──────────────────────────────────────────────────────────────

def test_plan_defaults_risk_select():
    h, _ = _make()
    action, risk = h.plan({"__caller_id": "u1"})
    assert risk == RISK_SELECT
    params = json.loads(action)
    assert params["limit"] == 20
    assert params["caller_id"] == "u1"


def test_plan_clamps_limit_to_100():
    h, _ = _make()
    action, risk = h.plan({"__caller_id": "u1", "limit": 999})
    params = json.loads(action)
    assert params["limit"] == 100
    assert risk == RISK_SELECT


def test_plan_invalid_decision_returns_deny():
    h, _ = _make()
    _, risk = h.plan({"__caller_id": "u1", "decision": "MAYBE"})
    assert risk == RISK_DENY


def test_plan_missing_caller_id_stores_empty_string():
    h, _ = _make()
    action, risk = h.plan({"limit": 10})
    params = json.loads(action)
    assert params["caller_id"] == ""
    assert risk == RISK_SELECT


def test_plan_preserves_filters():
    h, _ = _make()
    action, _ = h.plan({
        "__caller_id": "admin",
        "limit": 5,
        "user_id": "alice",
        "decision": "DENY",
        "start_date": "2026-01-01",
        "end_date": "2026-06-04",
    })
    params = json.loads(action)
    assert params["user_id"] == "alice"
    assert params["decision"] == "DENY"
    assert params["start_date"] == "2026-01-01"
    assert params["end_date"] == "2026-06-04"


# ── execute() 테스트 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_empty_caller_id_denied():
    h, _ = _make(roles=["admin"])
    result = await h.execute(json.dumps({"caller_id": "", "limit": 20}), RISK_SELECT)
    assert "권한 없음" in result


@pytest.mark.asyncio
async def test_execute_non_admin_denied():
    h, _ = _make(roles=["viewer"])
    result = await h.execute(
        json.dumps({"caller_id": "u1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "권한 없음" in result


@pytest.mark.asyncio
async def test_execute_admin_empty_result():
    h, conn = _make(roles=["admin"], rows=[])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert result == "(결과 없음)"
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_execute_admin_formats_rows():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "created_at": "2026-06-04 10:00:00+00",
        "user_id": "alice",
        "gate_decision": "DENY",
        "generated_sql": "SELECT * FROM employees",
        "reason": "capability 미부여",
    }[k]
    h, _ = _make(roles=["admin"], rows=[row])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "alice" in result
    assert "DENY" in result


@pytest.mark.asyncio
async def test_execute_db_error_returns_error_message():
    fga = _fga(["admin"])
    pool = MagicMock()

    @asynccontextmanager
    async def _bad_acquire():
        raise Exception("connection failed")
        yield  # noqa: unreachable

    pool.acquire = _bad_acquire
    h = AuditHistoryToolHandler(fga_client=fga, app_pool=pool)
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert "오류" in result
```

- [ ] **Step 2: 실패 확인**

```
.venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v
```

예상: `ERROR` — `ModuleNotFoundError: No module named 'app.graph.tools.audit_history_tool'`

- [ ] **Step 3: 구현 파일 작성**

`app/graph/tools/audit_history_tool.py` 신규 생성:

```python
"""감사 이력 조회 도구 핸들러 (ADR-0040). 관리자 전용 gate_audit_log 조회.

plan()은 LLM 인자를 검증해 params_json + RISK_SELECT를 반환한다.
execute()는 FGA admin 역할 확인 후 gate_audit_log를 SELECT한다.
caller_id는 tool_gate_node가 __caller_id 키로 주입한다.
"""
import json

import asyncpg
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from core.fga.client import FGAClient
from core.sql.risk import RISK_DENY, RISK_SELECT

_VALID_DECISIONS = frozenset({"ALLOW", "DENY", "JUSTIFY_AND_APPROVE"})
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_DESCRIPTION = (
    "감사 이력(게이트 결정·SQL 실행 사유)을 조회합니다. 관리자 전용. "
    "limit(건수 기본 20 최대 100), user_id(유저 필터), "
    "decision(ALLOW/DENY/JUSTIFY_AND_APPROVE), "
    "start_date/end_date(YYYY-MM-DD) 인자를 조합해 최신순으로 반환합니다."
)

_QUERY = (
    "SELECT user_id, department, question, generated_sql, sql_risk, "
    "gate_decision, reason, created_at "
    "FROM gate_audit_log "
    "WHERE ($1::text IS NULL OR user_id = $1) "
    "  AND ($2::text IS NULL OR gate_decision = $2) "
    "  AND ($3::date IS NULL OR created_at::date >= $3::date) "
    "  AND ($4::date IS NULL OR created_at::date <= $4::date) "
    "ORDER BY created_at DESC LIMIT $5"
)


class _Input(BaseModel):
    limit: int = Field(default=_DEFAULT_LIMIT, description="반환 건수 (최대 100)")
    user_id: str | None = Field(default=None, description="특정 유저 ID 필터")
    decision: str | None = Field(
        default=None, description="ALLOW / DENY / JUSTIFY_AND_APPROVE"
    )
    start_date: str | None = Field(default=None, description="시작 날짜 YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="종료 날짜 YYYY-MM-DD")


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    lines = []
    for r in rows:
        ts = str(r["created_at"])[:16]
        sql_preview = str(r["generated_sql"])[:60]
        lines.append(
            f"[{ts}] {r['user_id']} | {r['gate_decision']} | "
            f"{sql_preview} | 사유: {r['reason']}"
        )
    return "\n".join(lines)


class AuditHistoryToolHandler:
    name = "query_audit_history"

    def __init__(self, *, fga_client: FGAClient, app_pool: asyncpg.Pool) -> None:
        self._fga = fga_client
        self._pool = app_pool
        self.tool = StructuredTool.from_function(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda **_: "",
            args_schema=_Input,
        )

    def plan(self, args: dict) -> tuple[str, str]:
        caller_id = args.get("__caller_id", "")
        try:
            limit = min(int(args.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT
        decision = args.get("decision")
        if decision is not None and decision not in _VALID_DECISIONS:
            return f"잘못된 decision 값: {decision!r}", RISK_DENY
        params = {
            "caller_id": caller_id,
            "limit": limit,
            "user_id": args.get("user_id"),
            "decision": decision,
            "start_date": args.get("start_date"),
            "end_date": args.get("end_date"),
        }
        return json.dumps(params, ensure_ascii=False), RISK_SELECT

    async def execute(self, planned_action: str, risk: str) -> str:
        try:
            params = json.loads(planned_action)
        except Exception:
            return "감사 이력 조회 오류: 파라미터 파싱 실패"
        caller_id = params.get("caller_id", "")
        if not caller_id:
            return "권한 없음: 감사 이력은 관리자만 조회할 수 있습니다."
        try:
            roles = await self._fga.user_roles(caller_id)
        except Exception:
            return "권한 없음: 역할 조회 실패"
        if "admin" not in roles:
            return "권한 없음: 감사 이력은 관리자만 조회할 수 있습니다."
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    _QUERY,
                    params.get("user_id"),
                    params.get("decision"),
                    params.get("start_date"),
                    params.get("end_date"),
                    params.get("limit", _DEFAULT_LIMIT),
                )
            return _format_rows(list(rows))
        except Exception as exc:
            return f"감사 이력 조회 오류: {type(exc).__name__}"
```

- [ ] **Step 4: 테스트 통과 확인**

```
.venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v
```

예상: 모든 테스트 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app/graph/tools/audit_history_tool.py tests/app/graph/tools/test_audit_history_tool.py
git commit -m "feat(audit_history_tool): AuditHistoryToolHandler 구현 및 단위 테스트"
```

---

### Task 3: Registry에 등록

**Files:**
- Modify: `app/graph/tools/registry.py`
- Modify: `tests/app/graph/tools/test_registry.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/test_registry.py` 전체를 다음으로 교체:

```python
from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry


def test_registry_includes_all_tools():
    reg = build_tool_registry(
        llm=MagicMock(), sql_pool=MagicMock(),
        fga_client=MagicMock(), app_pool=MagicMock(),
    )
    assert "query_business_data" in reg.handlers
    assert "manage_permission" in reg.handlers
    assert "query_audit_history" in reg.handlers
    names = {t.name for t in reg.tool_defs}
    assert names == {"query_business_data", "manage_permission", "query_audit_history"}
```

- [ ] **Step 2: 실패 확인**

```
.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v
```

예상: `FAILED` — `TypeError: build_tool_registry() got an unexpected keyword argument 'app_pool'`

- [ ] **Step 3: registry.py 수정**

`app/graph/tools/registry.py` 전체를 다음으로 교체:

```python
"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from app.graph.tools.audit_history_tool import AuditHistoryToolHandler
from app.graph.tools.sql_tool import SqlToolHandler
from app.graph.tools.permission_tool import PermissionToolHandler


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolHandler
    tool_defs: list[BaseTool]   # bind_tools용


def build_tool_registry(
    *, llm: LLMClient, sql_pool, sql_rw_pool=None, fga_client: FGAClient, app_pool=None
) -> ToolRegistry:
    sql = SqlToolHandler(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool)
    permission = PermissionToolHandler(
        llm=llm, fga_client=fga_client, validator=PermissionValidator.from_config()
    )
    audit = AuditHistoryToolHandler(fga_client=fga_client, app_pool=app_pool)
    handlers = {sql.name: sql, permission.name: permission, audit.name: audit}
    tool_defs = [sql.tool, permission.tool, audit.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)
```

- [ ] **Step 4: 테스트 통과 확인**

```
.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v
```

예상: `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app/graph/tools/registry.py tests/app/graph/tools/test_registry.py
git commit -m "feat(registry): query_audit_history 등록, app_pool 파라미터 추가"
```

---

### Task 4: `build_graph` + `chat.py` 배선

**Files:**
- Modify: `app/graph/builder.py`
- Modify: `app/api/chat.py`
- Modify: `tests/app/graph/test_builder.py`

- [ ] **Step 1: test_builder.py 기존 호출에 `app_pool` 추가**

`tests/app/graph/test_builder.py` 안의 모든 `build_graph(` 호출을 찾아 `app_pool=AsyncMock()` 인자를 추가한다.

```
grep -n "build_graph(" tests/app/graph/test_builder.py
```

각 호출 줄의 마지막 인자 뒤에 `app_pool=AsyncMock(),`을 추가. 예:

```python
# 변경 전
graph = build_graph(
    retriever=mock_retriever, llm=mock_llm, fga_client=_fga([], []),
    audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(),
)

# 변경 후
graph = build_graph(
    retriever=mock_retriever, llm=mock_llm, fga_client=_fga([], []),
    audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), app_pool=AsyncMock(),
)
```

- [ ] **Step 2: 실패 확인**

```
.venv/bin/python -m pytest tests/app/graph/test_builder.py -v 2>&1 | head -30
```

예상: `TypeError: build_graph() got an unexpected keyword argument 'app_pool'`

- [ ] **Step 3: builder.py 수정**

`app/graph/builder.py`의 `build_graph` 시그니처에 `app_pool: Any = None` 추가하고, `build_tool_registry` 호출에 `app_pool=app_pool` 전달:

```python
# 시그니처 변경 — sql_rw_pool 바로 다음 줄에 추가
    app_pool: Any = None,

# build_tool_registry 호출 변경
    registry = build_tool_registry(
        llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool,
        fga_client=fga_client, app_pool=app_pool,
    )
```

- [ ] **Step 4: test_builder 통과 확인**

```
.venv/bin/python -m pytest tests/app/graph/test_builder.py -v
```

예상: 모든 테스트 `PASSED`

- [ ] **Step 5: chat.py 수정**

`app/api/chat.py`의 `build_graph(` 호출에 `app_pool=pool` 추가:

```python
# 변경 전
        graph = build_graph(
            ...
            checkpointer=checkpointer, audit_sink=audit_sink, sql_pool=sql_pool,
            sql_rw_pool=sql_rw_pool,
        )

# 변경 후
        graph = build_graph(
            ...
            checkpointer=checkpointer, audit_sink=audit_sink, sql_pool=sql_pool,
            sql_rw_pool=sql_rw_pool, app_pool=pool,
        )
```

- [ ] **Step 6: 전체 테스트 통과 확인**

```
.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

예상: 모든 테스트 `PASSED`

- [ ] **Step 7: 커밋**

```bash
git add app/graph/builder.py app/api/chat.py tests/app/graph/test_builder.py
git commit -m "feat(builder): app_pool 파라미터 추가 및 chat.py 배선"
```

---

### Task 5: ADR-0040 작성 및 인덱스 갱신

**Files:**
- Create: `docs/superpowers/decisions/ADR-0040-audit-history-tool.md`
- Auto-update: `docs/superpowers/decisions/README.md` (스크립트로)

- [ ] **Step 1: ADR 파일 작성**

`docs/superpowers/decisions/ADR-0040-audit-history-tool.md` 신규 생성:

```markdown
# ADR-0040: query_audit_history 도구 — ReAct 루프 내 감사 이력 조회

> **Status**: 🟢 적용완료

## 컨텍스트

관리자가 채팅 인터페이스를 통해 `gate_audit_log`를 자연어로 조회할 수 있어야 한다.
별도 대시보드 없이 기존 ReAct 루프에 통합하는 것이 목표다.

## 결정

`query_audit_history` ToolHandler를 기존 패턴(ADR-0023)으로 추가한다.

**주요 결정:**
- 위험도: `RISK_SELECT` 재사용 → 게이트 자동 ALLOW, 추가 FGA 튜플 불필요
- admin 체크: `execute()` 안에서 `fga_client.user_roles()` 조회 — 인터페이스 변경 없이 처리
- caller_id 전달: `tool_gate_node`가 `{**args, "__caller_id": user_id}` 주입 → `plan()`이 `params_json`에 포함
- 멀티파라미터: `StructuredTool` + Pydantic `_Input` 스키마 — LLM이 구조화된 인자를 직접 채움

## 대안

- **별도 read_node (거부)**: 그래프 노드/엣지 추가 복잡도가 크고, ALLOW 경로로 충분히 처리 가능
- **RISK_GRANT 재사용 (거부)**: 권한 부여와 조회를 같은 capability에 묶는 것은 의미론적으로 부적절
- **execute() 인터페이스에 user_id 추가 (거부)**: 기존 SqlToolHandler·PermissionToolHandler 모두 수정 필요

## 결과

- 관리자(FGA `role:admin` member)만 조회 가능
- 비관리자는 gate ALLOW 후 execute()에서 "권한 없음" 메시지 반환
- `gate_audit_log` 조회 자체도 audit 기록됨 (gate ALLOW 결정으로 남음)
```

- [ ] **Step 2: ADR 인덱스 갱신**

```
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m scripts.gen_adr_index
```

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/decisions/ADR-0040-audit-history-tool.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0040 query_audit_history 도구 결정 기록"
```

---

## 완료 기준 (DoD)

- [ ] `test_caller_id_injected_into_plan` 통과
- [ ] `tests/app/graph/tools/test_audit_history_tool.py` 전체 통과 (10개 테스트)
- [ ] `test_registry_includes_all_tools` 통과
- [ ] `tests/app/graph/test_builder.py` 전체 통과
- [ ] `tests/ -v` 전체 green
- [ ] ADR-0040 작성 및 README 갱신

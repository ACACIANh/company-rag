# 도구 결과/감사요약 분리 (ToolResult) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 각 도구가 감사로그용 짧은 요약을 데이터를 쥔 시점에 직접 생성하도록 `execute` 반환을 `str`→`ToolResult(text, summary)`로 분리하고, 읽기 단계의 정규식 추측(`_clean_result`)을 제거한다.

**Architecture:** `app/graph/tools/base.py`에 불변 값 객체 `ToolResult`를 추가하고 `ToolAgent.execute` 반환 타입을 바꾼다. 3개 핸들러(SqlAgent/AuditAgent/PermissionAgent)가 각 분기에서 `ToolResult`를 반환한다. 2개 노드(tool_gate/justify_execute)가 `result.text`를 ToolMessage에, `result.summary`를 감사로그에 쓴다. 감사 표시 단계는 `result_summary`를 이스케이프+컷만 한다.

**Tech Stack:** Python 3.11, asyncpg, LangChain/LangGraph, pytest. 작업 디렉토리는 `backend/`, 인터프리터는 `.venv/bin/python`.

**작업 규칙:** CLAUDE.md 규칙 6(수술적 변경) 준수 — 명시된 줄만 수정.

---

### Task 1: `ToolResult` 값 객체 + Protocol 시그니처

**Files:**
- Modify: `backend/app/graph/tools/base.py`
- Test: `backend/tests/app/graph/tools/test_base.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/app/graph/tools/test_base.py`:

```python
import dataclasses
import pytest

from app.graph.tools.base import ToolResult


def test_tool_result_holds_text_and_summary():
    r = ToolResult(text="전체 표", summary="12행 조회")
    assert r.text == "전체 표"
    assert r.summary == "12행 조회"


def test_tool_result_is_frozen():
    r = ToolResult(text="a", summary="b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.text = "c"  # type: ignore[misc]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v`
Expected: FAIL — `ImportError: cannot import name 'ToolResult'`

- [ ] **Step 3: 구현**

`backend/app/graph/tools/base.py`를 다음으로 교체한다(파일 전체):

```python
"""도구 에이전트 추상화 (ADR-0023) — app 계층(LangChain 인지).

도구 = LLM에 노출할 LangChain Tool 정의 + 서버측 에이전트(plan/execute).
plan은 인자를 '구체화된 동작 + 위험도'로 바꾼다(SQL이면 생성된 SQL + 위험도 등급).
execute는 그 동작을 실행해 결과를 만든다. 게이트는 plan과 execute 사이에서 돈다.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolResult:
    """도구 실행 결과. text=사용자 노출 전체 텍스트, summary=감사로그용 짧은 한 줄 (ADR-0052)."""

    text: str
    summary: str


@runtime_checkable
class ToolAgent(Protocol):
    name: str
    label: str

    def plan(self, args: dict) -> tuple[str, str]:
        """도구 인자 → (구체화된 동작, core.sql.risk 위험도 등급)."""
        ...

    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        """구체화된 동작 실행 → ToolResult. risk는 실행 경로(읽기/쓰기) 선택에 쓴다."""
        ...
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/graph/tools/base.py backend/tests/app/graph/tools/test_base.py
git commit -m "feat(tools): ToolResult 값 객체 추가, execute 반환 타입 ToolResult로"
```

---

### Task 2: SqlAgent.execute → ToolResult

**Files:**
- Modify: `backend/app/graph/tools/sql_tool.py:69-85`
- Test: `backend/tests/app/graph/tools/test_sql_tool.py`

> **기존 헬퍼/단언 (이미 파일에 존재):** `_pool(fetch_return=None, execute_return="UPDATE 2")`가 `(pool, conn)` 튜플을 반환한다. `from core.sql.risk import RISK_UPDATE_DELETE` 도 이미 import됨. 기존 테스트는 `assert "3" in result`, `assert "오류" in result`처럼 **execute 반환을 str로 단언**하므로 이 Task에서 깨진다 — Step 3 이후 갱신한다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/app/graph/tools/test_sql_tool.py` 상단에 `from app.graph.tools.base import ToolResult` import를 추가하고, 파일 끝에 신규 테스트를 추가한다(기존 `_pool` 헬퍼 재사용):

```python
@pytest.mark.asyncio
async def test_execute_select_returns_toolresult_with_row_count():
    ro, _ = _pool(fetch_return=[{"emp_id": 1, "name": "a"}, {"emp_id": 2, "name": "b"}])
    agent = SqlAgent(llm=MagicMock(), sql_pool=ro)
    result = await agent.execute("SELECT * FROM business.employees", RISK_SELECT)
    assert isinstance(result, ToolResult)
    assert result.summary == "2행 조회"
    assert "emp_id" in result.text  # 마크다운 표


@pytest.mark.asyncio
async def test_execute_update_returns_toolresult_with_change_count():
    ro, _ = _pool()
    rw, _ = _pool(execute_return="UPDATE 3")
    agent = SqlAgent(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)
    result = await agent.execute("UPDATE business.employees SET salary=1 WHERE emp_id='x'", RISK_UPDATE_DELETE)
    assert isinstance(result, ToolResult)
    assert result.summary == "3행 변경"
    assert "3개 행" in result.text


@pytest.mark.asyncio
async def test_execute_select_error_returns_toolresult():
    ro, ro_conn = _pool()
    ro_conn.fetch = AsyncMock(side_effect=RuntimeError("boom"))
    agent = SqlAgent(llm=MagicMock(), sql_pool=ro)
    result = await agent.execute("SELECT 1", RISK_SELECT)
    assert isinstance(result, ToolResult)
    assert result.text.startswith("SQL 실행 오류")
    assert result.summary == result.text
```

`RISK_SELECT`가 파일에 import돼 있지 않으면 상단 import를 `from core.sql.risk import RISK_SELECT, RISK_UPDATE_DELETE`로 보강한다.

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v`
Expected: FAIL — `execute`가 `str`을 반환해 `isinstance(result, ToolResult)` False

- [ ] **Step 3: 구현**

`backend/app/graph/tools/sql_tool.py`의 `execute`(69-85줄)를 교체한다. 파일 상단 import에 `from app.graph.tools.base import ToolResult`를 추가한다:

```python
    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        if risk == RISK_UPDATE_DELETE:
            if self._rw_pool is None:
                msg = "SQL 실행 오류: 쓰기 풀 미구성"
                return ToolResult(text=msg, summary=msg)
            try:
                async with self._rw_pool.acquire() as conn:
                    async with conn.transaction():
                        status = await conn.execute(planned_action)
                n = _affected_rows(status)
                return ToolResult(text=f"{n}개 행이 변경되었습니다.", summary=f"{n}행 변경")
            except Exception as exc:
                msg = f"SQL 실행 오류: {type(exc).__name__}"
                return ToolResult(text=msg, summary=msg)
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(planned_action)
            limited = list(rows)[:self._row_limit]
            return ToolResult(text=_format_rows(limited), summary=f"{len(limited)}행 조회")
        except Exception as exc:
            msg = f"SQL 실행 오류: {type(exc).__name__}"
            return ToolResult(text=msg, summary=msg)
```

- [ ] **Step 4: 통과 확인**

먼저 기존 테스트의 str 단언을 갱신한다:
- `test_update_uses_rw_pool_and_reports_rows`의 `assert "3" in result` → `assert "3" in result.text`
- `test_update_without_rw_pool_errors`의 `assert "오류" in result` → `assert "오류" in result.text`
- 그 외 `result`를 str로 다루는 기존 execute 단언이 있으면 모두 `result.text`로 변경

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v`
Expected: PASS (기존 + 신규 전부 통과)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/graph/tools/sql_tool.py backend/tests/app/graph/tools/test_sql_tool.py
git commit -m "feat(sql): SqlAgent.execute가 ToolResult 반환 (행수 요약)"
```

---

### Task 3: AuditAgent.execute → ToolResult + `_clean_result` 제거

**Files:**
- Modify: `backend/app/graph/tools/audit_history_tool.py` (execute 163-191, _format_rows 109-127, _clean_result 65-76 삭제)
- Test: `backend/tests/app/graph/tools/test_audit_history_tool.py`

> **기존 헬퍼/단언 (이미 파일에 존재):** `_fga(has_access=True)`, `_pool(rows=None)→(pool,conn)`, `_make(has_access=True, rows=None)→(agent, conn)`. 9번째 줄에서 `_clean_result`를 import하고, 164-183줄에 `_clean_result` 전용 테스트 4개가 있다 — 함수 삭제와 함께 **이 import와 테스트 4개를 제거**해야 한다. execute 단언들(`"권한 없음" in result`, `result == "(결과 없음)"`, `"joohwan" in result` 등)은 str 가정이라 갱신 대상.

- [ ] **Step 1: 실패 테스트 작성 + 기존 테스트 정리**

(1-1) 상단에 `from app.graph.tools.base import ToolResult` import 추가.

(1-2) 신규 테스트 추가 — `_format_rows` 이스케이프 + execute의 ToolResult/요약:

```python
def test_format_rows_escapes_pipe_in_result_summary():
    rows = [{
        "created_at": "2026-06-05 10:00:00", "user_id": "user-admin",
        "department": "c_level", "role": "", "generated_sql": "{}",
        "gate_decision": "ALLOW", "reason": "x",
        "result_summary": "a | b | c",  # 레거시 깨진 행 모사
    }]
    out = _format_rows(rows)
    assert "a \\| b \\| c" in out  # 파이프 이스케이프로 표가 깨지지 않음


@pytest.mark.asyncio
async def test_execute_returns_toolresult_with_count_summary():
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "created_at": "2026-06-05 10:00:00", "user_id": "user-a", "department": "",
        "role": "", "gate_decision": "ALLOW", "generated_sql": "{}",
        "reason": "r", "result_summary": "x",
    }[k]
    h, _ = _make(has_access=True, rows=[row])
    result = await h.execute(
        json.dumps({"caller_id": "admin1", "limit": 20, "user_id": None,
                    "decision": None, "start_date": None, "end_date": None}),
        RISK_SELECT,
    )
    assert isinstance(result, ToolResult)
    assert result.summary == "감사이력 1건 조회"
```

(1-3) `_format_rows`는 이미 import돼 있다(없으면 상단 import 보강). `_clean_result` import(9줄)와 `_clean_result` 테스트 블록(164-183줄, 테스트 4개)을 **삭제**한다.

(1-4) 기존 execute 테스트의 str 단언을 `.text`로 갱신:
- `test_execute_empty_caller_id_denied`: `assert "권한 없음" in result` → `assert result.summary == "권한 없음"`
- `test_execute_non_admin_denied`: `assert "권한 없음" in result` → `assert result.summary == "권한 없음"`
- `test_execute_admin_empty_result`: `assert result == "(결과 없음)"` → `assert result.text == "(결과 없음)"` (이어서 `assert result.summary == "감사이력 0건 조회"` 추가)
- `test_execute_admin_formats_rows`: `"joohwan"/"DENY"/"|"/"개발"/"c_level" in result` → 모두 `in result.text`

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v`
Expected: FAIL — execute가 str 반환, `_format_rows`가 `_clean_result`로 파이프를 제거해 이스케이프 미적용

- [ ] **Step 3: 구현**

(3-1) `backend/app/graph/tools/audit_history_tool.py` 상단 import에 `from app.graph.tools.base import ToolResult` 추가.

(3-2) `_clean_result`(65-76줄) **삭제**.

(3-3) `_format_rows`(116-126줄 루프 내부)의 `result_summary` 처리 2줄을 교체. 기존:
```python
        result_raw = str(r["result_summary"] or "").replace("\n", " ").replace("\r", "")
        result_col = _clean_result(result_raw)
```
교체 후:
```python
        result_col = str(r["result_summary"] or "").replace("\n", " ").replace("\r", "").replace("|", "\\|")[:80]
```

(3-4) `execute`(163-191줄)의 반환들을 `ToolResult`로 감싼다:
```python
    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        try:
            params = json.loads(planned_action)
        except Exception:
            msg = "감사 이력 조회 오류: 파라미터 파싱 실패"
            return ToolResult(text=msg, summary=msg)
        caller_id = params.get("caller_id", "")
        if not caller_id:
            return ToolResult(
                text="권한 없음: 감사 이력은 관리자만 조회할 수 있습니다.", summary="권한 없음"
            )
        try:
            has_access = await self._fga.check(
                f"user:{caller_id}", "justify_grant", "capability:admin"
            )
        except Exception:
            return ToolResult(text="권한 없음: 역할 조회 실패", summary="권한 없음")
        if not has_access:
            return ToolResult(
                text="권한 없음: 감사 이력은 관리자만 조회할 수 있습니다.", summary="권한 없음"
            )
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
            rows = list(rows)
            return ToolResult(text=_format_rows(rows), summary=f"감사이력 {len(rows)}건 조회")
        except Exception as exc:
            msg = f"감사 이력 조회 오류: {type(exc).__name__}"
            return ToolResult(text=msg, summary=msg)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v`
Expected: PASS (기존 테스트가 `_clean_result`를 직접 호출했다면 그 테스트는 삭제하라 — 함수가 제거됨)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/graph/tools/audit_history_tool.py backend/tests/app/graph/tools/test_audit_history_tool.py
git commit -m "feat(audit): AuditAgent.execute가 ToolResult 반환, _clean_result 정규식 제거"
```

---

### Task 4: PermissionAgent.execute → ToolResult

**Files:**
- Modify: `backend/app/graph/tools/permission_tool.py:78-114`
- Test: `backend/tests/app/graph/tools/test_permission_tool.py`

> **기존 헬퍼/단언 (이미 파일에 존재):** `_validator()`, `_llm(reply)`. execute 테스트 3개(`test_execute_grant_calls_grant_tuple` 88줄, `test_execute_revoke_calls_revoke_tuple` 98줄, `test_execute_query_self_returns_snapshot` 107줄)가 `assert "완료" in result`, `assert "user-joohwan" in result` 등 str로 단언 → str→`.text` 갱신 대상.

- [ ] **Step 1: 실패 테스트 작성 + 기존 단언 갱신**

(1-1) 상단에 `from app.graph.tools.base import ToolResult` import 추가.

(1-2) 기존 execute 테스트의 str 단언을 `.text`/`.summary`로 갱신:
- `test_execute_grant_calls_grant_tuple`: `assert "완료" in result` → 다음 2줄로 교체
  ```python
  assert result.text == "완료: grant user:user-joohwan member department:개발"
  assert result.summary == "완료: grant user:user-joohwan member department:개발"
  ```
- `test_execute_query_self_returns_snapshot`: `"user-joohwan"/"개발"/"/engineering/specs"/"SQL/관리 권한" in result` → 모두 `in result.text`. 이어서 한 줄 추가:
  ```python
  assert result.summary == "권한 스냅샷 조회(user-joohwan)"
  ```

(1-3) 신규 테스트 추가(스냅샷 요약·grant 요약은 위에서 커버됨 — ToolResult 타입만 한 줄로 추가 확인):
```python
@pytest.mark.asyncio
async def test_execute_returns_toolresult_type():
    fga = MagicMock(); fga.grant_tuple = AsyncMock()
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("grant user:u1 member department:개발", "RISK_GRANT")
    assert isinstance(result, ToolResult)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v`
Expected: FAIL — execute가 str 반환

- [ ] **Step 3: 구현**

`backend/app/graph/tools/permission_tool.py` 상단 import에 `from app.graph.tools.base import ToolResult` 추가. `execute`(78-114줄)의 모든 반환을 감싼다:

```python
    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        if planned_action.startswith("query "):
            parts = planned_action.split(" ", 2)
            if len(parts) != 3:
                msg = "권한 조회 오류: 잘못된 동작 형식"
                return ToolResult(text=msg, summary=msg)
            _, caller, target = parts
            if target != caller:
                try:
                    admin_ok = await self._fga.check(f"user:{caller}", "justify_grant", "capability:admin")
                except Exception:
                    return ToolResult(text="권한 없음: 관리자 확인 실패", summary="권한 없음")
                if not admin_ok:
                    return ToolResult(text="권한 없음: 타인 조회는 관리자만 가능합니다.", summary="권한 없음")
            try:
                departments = await self._fga.user_departments(target)
                roles = await self._fga.user_roles(target)
                folders = await self._fga.get_readable_folders(target)
                capabilities = await _resolve_capabilities(self._fga.check, target)
                tables = await self._fga.user_accessible_tables(target)
            except Exception as exc:
                msg = f"권한 조회 오류: {type(exc).__name__}"
                return ToolResult(text=msg, summary=msg)
            return ToolResult(
                text=_format_permission_snapshot(target, departments, roles, folders, capabilities, tables),
                summary=f"권한 스냅샷 조회({target})",
            )

        parts = planned_action.split(" ")
        if len(parts) != 4:
            msg = "권한 실행 오류: 잘못된 동작 형식"
            return ToolResult(text=msg, summary=msg)
        action, subject, relation, object_ = parts
        try:
            if action == "grant":
                await self._fga.grant_tuple(subject, relation, object_)
            elif action == "revoke":
                await self._fga.revoke_tuple(subject, relation, object_)
            else:
                msg = "권한 실행 오류: 알 수 없는 action"
                return ToolResult(text=msg, summary=msg)
            done = f"완료: {planned_action}"
            return ToolResult(text=done, summary=done)
        except Exception as exc:
            msg = f"권한 실행 오류: {type(exc).__name__}"
            return ToolResult(text=msg, summary=msg)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v`
Expected: PASS (기존 테스트가 execute 반환을 str로 단언했다면 `.text`로 갱신)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/graph/tools/permission_tool.py backend/tests/app/graph/tools/test_permission_tool.py
git commit -m "feat(permission): PermissionAgent.execute가 ToolResult 반환"
```

---

### Task 5: 노드 배선 (tool_gate / justify_execute)

**Files:**
- Modify: `backend/app/graph/nodes/tool_gate.py:88-91`
- Modify: `backend/app/graph/nodes/justify_execute.py:30-33`
- Test: `backend/tests/app/graph/nodes/test_tool_gate.py:23-27`, `backend/tests/app/graph/nodes/test_justify_execute.py:8-12`

- [ ] **Step 1: 노드 테스트의 페이크 핸들러를 ToolResult 반환으로 갱신**

`backend/tests/app/graph/nodes/test_tool_gate.py` 상단에 import 추가:
```python
from app.graph.tools.base import ToolResult
```
`_handler`(23-27줄)를 교체:
```python
def _handler(planned, risk, result="rows"):
    h = MagicMock()
    h.plan.return_value = (planned, risk)
    h.execute = AsyncMock(return_value=ToolResult(text=result, summary=result))
    return h
```

`backend/tests/app/graph/nodes/test_justify_execute.py` 상단에 import 추가:
```python
from app.graph.tools.base import ToolResult
```
`_registry`(8-12줄)의 10줄을 교체:
```python
    h.execute = AsyncMock(return_value=ToolResult(text="급여 결과", summary="급여 결과"))
```

- [ ] **Step 2: 실패 확인 (노드 코드는 아직 str 가정)**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py tests/app/graph/nodes/test_justify_execute.py -v`
Expected: FAIL — 노드가 `ToolMessage(content=result)`에 `ToolResult` 객체를 넣고 `str(result)[:200]`로 repr을 저장 → `"42" in content`와 `result_summary == "42"` 실패

- [ ] **Step 3: 노드 구현 교체**

`backend/app/graph/nodes/tool_gate.py`의 88-91줄을 교체:
```python
        if decision == DECISION_ALLOW:
            result = await handler.execute(planned_action, risk)
            new_messages.append(ToolMessage(content=result.text, tool_call_id=tc["id"]))
            result_summary = result.summary
```

`backend/app/graph/nodes/justify_execute.py`의 30-33줄을 교체:
```python
            result = await handler.execute(p["planned_action"], p["risk"])
            messages.append(ToolMessage(content=result.text, tool_call_id=p["id"]))
            reason = state.get("justification", "")
            result_summary = result.summary
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py tests/app/graph/nodes/test_justify_execute.py -v`
Expected: PASS

- [ ] **Step 5: 전체 도구·노드 테스트 회귀 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/app/graph/tools tests/app/graph/nodes -v`
Expected: PASS (전부 통과)

- [ ] **Step 6: 커밋**

```bash
git add backend/app/graph/nodes/tool_gate.py backend/app/graph/nodes/justify_execute.py \
        backend/tests/app/graph/nodes/test_tool_gate.py backend/tests/app/graph/nodes/test_justify_execute.py
git commit -m "feat(nodes): tool_gate·justify_execute가 ToolResult.text/.summary 사용"
```

---

### Task 6: ADR + CLAUDE.md + 인덱스 + eval 회귀

**Files:**
- Create: `backend/docs/superpowers/decisions/ADR-0052-tool-result-audit-summary-separation.md`
- Modify: `backend/CLAUDE.md` (핵심 아키텍처 결정 섹션)
- Modify: `backend/docs/superpowers/decisions/README.md` (자동 생성 — 직접 편집 금지, 스크립트로 갱신)

- [ ] **Step 1: ADR 작성**

`backend/docs/superpowers/decisions/_template.md`를 참고해 `ADR-0052-tool-result-audit-summary-separation.md`를 작성한다. 필수: 제목 바로 아래 `> **Status**: 🟢 적용완료` 한 줄. 내용 요지:
- **맥락**: `execute -> str`을 `str(result)[:200]`로 잘라 감사요약 재사용 → 감사조회 결과가 자기참조로 적재되어 `result_summary` 가독성 붕괴. 읽기 단계 `_clean_result` 정규식 추측이 SELECT 결과도 깨뜨림.
- **결정**: `execute` 반환을 `ToolResult(text, summary)`로 분리. 각 핸들러가 데이터를 쥔 시점에 짧은 요약 생성(`"N행 조회"`, `"감사이력 N건 조회"`, `"권한 스냅샷 조회(uid)"` 등). 읽기 단계 `_clean_result` 제거, 표시 단계는 이스케이프+80자 컷만.
- **결과**: 자기참조 노이즈 제거. 스키마 무변경. **레거시 행은 백필 불가**(forward-only). 웹 위젯 렌더링은 범위 밖.
- **대안**: `audit_summary()` 별도 메서드 — 완성된 문자열 재파싱으로 안티패턴 잔존, 기각.

- [ ] **Step 2: 인덱스 재생성**

Run: `cd backend && .venv/bin/python -m scripts.gen_adr_index`
Expected: `decisions/README.md` 재생성, ADR-0052 포함

- [ ] **Step 3: CLAUDE.md 갱신**

`backend/CLAUDE.md`의 "## 핵심 아키텍처 결정" 섹션에 한 줄 추가:
```markdown
- 도구 결과: `ToolAgent.execute`는 `ToolResult(text, summary)` 반환. text=사용자 노출, summary=감사로그(`result_summary`)용 짧은 한 줄. 각 핸들러가 데이터 시점에 요약 생성(읽기단계 정규식 추측 제거). 상세: ADR-0052.
```

- [ ] **Step 4: eval 회귀 점수 확인 (DoD)**

Run: `cd backend && .venv/bin/python -m tests.eval.runner`
Expected: 점수 출력. 직전 대비 하락 시 원인 명시. (실행 불가 환경이면 사유 기록)

- [ ] **Step 5: 커밋**

```bash
git add backend/docs/superpowers/decisions/ADR-0052-tool-result-audit-summary-separation.md \
        backend/docs/superpowers/decisions/README.md backend/CLAUDE.md
git commit -m "docs(adr): ADR-0052 도구 결과/감사요약 분리 (ToolResult)"
```

---

## Self-Review (작성자 체크)

- **Spec 커버리지**: ToolResult(Task1) · 핸들러별 요약 SqlAgent(T2)/AuditAgent(T3)/PermissionAgent(T4) · 노드 배선(T5) · `_clean_result` 삭제(T3) · `_merge_system_pairs` 유지(T3에서 미수정) · 에러 ToolResult(각 핸들러) · 테스트(각 Task) · ADR/CLAUDE.md(T6) · 레거시 백필 불가 명시(ADR T6). 모두 매핑됨.
- **타입 일관성**: `ToolResult(text, summary)` 속성명이 T1 정의와 T2~T5 사용처에서 일치. `execute(...) -> ToolResult` 시그니처 일관.
- **Placeholder 스캔**: 모든 코드 블록 실제 코드. `_fake_pool` 헬퍼는 기존 패턴 우선·미존재 시 최소 구현 제시.

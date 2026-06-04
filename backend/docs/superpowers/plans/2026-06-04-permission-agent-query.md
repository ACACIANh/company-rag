# PermissionAgent 개명 + 권한 조회 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `*ToolHandler` 클래스를 `*Agent`로 전면 개명하고, `PermissionAgent`에 권한 조회(`query`) 기능을 추가한다.

**Architecture:** `app/graph/tools/`의 세 에이전트 클래스(`SqlToolHandler`, `PermissionToolHandler`, `AuditHistoryToolHandler`)와 Protocol(`ToolHandler`)을 각각 `SqlAgent`, `PermissionAgent`, `AuditAgent`, `ToolAgent`로 개명한다. 이후 `PermissionAgent.plan()`에 `query` 액션을 추가하고 `execute()`에서 FGA 3종 조회(부서·역할·폴더)를 수행해 포맷된 스냅샷을 반환한다. 관리자 검증은 `AuditAgent` 동일 패턴으로 `execute()` 내부에서 수행한다.

**Tech Stack:** Python 3.11+, LangGraph, OpenFGA SDK (`openfga_sdk`), asyncpg, pytest-asyncio

---

## 파일 맵

| 파일 | 변경 내용 |
|------|----------|
| `app/graph/tools/base.py` | `ToolHandler` → `ToolAgent` |
| `app/graph/tools/sql_tool.py` | `SqlToolHandler` → `SqlAgent` |
| `app/graph/tools/audit_history_tool.py` | `AuditHistoryToolHandler` → `AuditAgent` |
| `app/graph/tools/permission_tool.py` | `PermissionToolHandler` → `PermissionAgent`, `query` 액션 추가 |
| `app/graph/tools/registry.py` | import + 인스턴스화 + 주석 일괄 반영 |
| `app/graph/prompts.py` | `PERMISSION_PARSE_PROMPT`에 `query` 지시 추가 |
| `tests/app/graph/tools/test_base.py` | `ToolHandler` → `ToolAgent` |
| `tests/app/graph/tools/test_sql_tool.py` | `SqlToolHandler` → `SqlAgent` |
| `tests/app/graph/tools/test_audit_history_tool.py` | `AuditHistoryToolHandler` → `AuditAgent` |
| `tests/app/graph/tools/test_permission_tool.py` | `PermissionToolHandler` → `PermissionAgent`, query 테스트 추가 |

---

### Task 1: `ToolAgent` Protocol 개명

**Files:**
- Modify: `app/graph/tools/base.py`
- Modify: `tests/app/graph/tools/test_base.py`

- [ ] **Step 1: 테스트 먼저 수정 — `ToolAgent` import**

`tests/app/graph/tools/test_base.py` 전체를 아래로 교체:

```python
import pytest

from app.graph.tools.base import ToolAgent


class _DummyAgent:
    name = "echo"
    def plan(self, args):
        return (args["text"], "select")
    async def execute(self, planned_action):
        return f"ran: {planned_action}"


@pytest.mark.asyncio
async def test_tool_agent_protocol_runtime_checkable():
    h = _DummyAgent()
    assert isinstance(h, ToolAgent)
    assert h.plan({"text": "hi"}) == ("hi", "select")
    assert await h.execute("hi") == "ran: hi"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v
```

기대 결과: `ImportError: cannot import name 'ToolAgent'`

- [ ] **Step 3: `base.py` 개명**

`app/graph/tools/base.py` 의 `class ToolHandler(Protocol):` 한 줄을 수정:

```python
@runtime_checkable
class ToolAgent(Protocol):
    name: str

    def plan(self, args: dict) -> tuple[str, str]:
        """도구 인자 → (구체화된 동작, core.sql.risk 위험도 등급)."""
        ...

    async def execute(self, planned_action: str, risk: str) -> str:
        """구체화된 동작 실행 → 결과 텍스트. risk는 실행 경로(읽기/쓰기) 선택에 쓴다."""
        ...
```

모듈 docstring 첫 줄 `ToolHandler` → `ToolAgent`도 수정:
```python
"""도구 에이전트 추상화 (ADR-0023) — app 계층(LangChain 인지).
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_base.py -v
```

기대 결과: `PASSED`

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/tools/base.py backend/tests/app/graph/tools/test_base.py
git commit -m "refactor: ToolHandler → ToolAgent Protocol 개명"
```

---

### Task 2: `SqlAgent` 개명

**Files:**
- Modify: `app/graph/tools/sql_tool.py:41`
- Modify: `tests/app/graph/tools/test_sql_tool.py`

- [ ] **Step 1: 테스트 import 수정**

`tests/app/graph/tools/test_sql_tool.py` 첫 번째 import 줄을 수정:

```python
from app.graph.tools.sql_tool import SqlAgent, _format_rows
```

파일 내 모든 `SqlToolHandler(` → `SqlAgent(` 로 치환 (총 5곳):

```bash
cd /Users/acacian/vscode/company-rag/backend && grep -n "SqlToolHandler" tests/app/graph/tools/test_sql_tool.py
```

각 줄의 `SqlToolHandler(` → `SqlAgent(` 로 수정. (예시: `h = SqlAgent(llm=MagicMock(), sql_pool=ro, sql_rw_pool=rw)`)

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v
```

기대 결과: `ImportError: cannot import name 'SqlAgent'`

- [ ] **Step 3: `sql_tool.py` 클래스명 수정**

`app/graph/tools/sql_tool.py:41` 의 `class SqlToolHandler:` → `class SqlAgent:`:

```python
class SqlAgent:
    name = "query_business_data"
```

모듈 docstring 첫 줄도 수정:
```python
"""SQL 조회 에이전트 (ADR-0023). NL 질문 → SQL → 위험도 → (게이트) → 실행.
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_sql_tool.py -v
```

기대 결과: 전체 `PASSED`

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/tools/sql_tool.py backend/tests/app/graph/tools/test_sql_tool.py
git commit -m "refactor: SqlToolHandler → SqlAgent 개명"
```

---

### Task 3: `AuditAgent` 개명

**Files:**
- Modify: `app/graph/tools/audit_history_tool.py:62`
- Modify: `tests/app/graph/tools/test_audit_history_tool.py`

- [ ] **Step 1: 테스트 import 수정**

`tests/app/graph/tools/test_audit_history_tool.py` 의 import 수정:

```python
from app.graph.tools.audit_history_tool import AuditAgent
```

파일 내 모든 `AuditHistoryToolHandler(` → `AuditAgent(` 로 치환 (총 2곳):

```bash
cd /Users/acacian/vscode/company-rag/backend && grep -n "AuditHistoryToolHandler" tests/app/graph/tools/test_audit_history_tool.py
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v
```

기대 결과: `ImportError: cannot import name 'AuditAgent'`

- [ ] **Step 3: `audit_history_tool.py` 클래스명 수정**

`app/graph/tools/audit_history_tool.py:62` 의 `class AuditHistoryToolHandler:` → `class AuditAgent:`:

```python
class AuditAgent:
    name = "query_audit_history"
```

모듈 docstring 첫 줄도 수정:
```python
"""감사 이력 조회 에이전트 (ADR-0040). 관리자 전용 gate_audit_log 조회.
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_audit_history_tool.py -v
```

기대 결과: 전체 `PASSED`

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/tools/audit_history_tool.py backend/tests/app/graph/tools/test_audit_history_tool.py
git commit -m "refactor: AuditHistoryToolHandler → AuditAgent 개명"
```

---

### Task 4: `PermissionAgent` 개명 (query 기능은 Task 6에서)

**Files:**
- Modify: `app/graph/tools/permission_tool.py:29`
- Modify: `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: 테스트 import 수정**

`tests/app/graph/tools/test_permission_tool.py` 의 import 수정:

```python
from app.graph.tools.permission_tool import PermissionAgent
```

파일 내 모든 `PermissionToolHandler(` → `PermissionAgent(` 로 치환 (총 6곳):

```bash
cd /Users/acacian/vscode/company-rag/backend && grep -n "PermissionToolHandler" tests/app/graph/tools/test_permission_tool.py
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v
```

기대 결과: `ImportError: cannot import name 'PermissionAgent'`

- [ ] **Step 3: `permission_tool.py` 클래스명 수정**

`app/graph/tools/permission_tool.py:29` 의 `class PermissionToolHandler:` → `class PermissionAgent:`:

```python
class PermissionAgent:
    name = "manage_permission"
```

모듈 docstring 첫 줄도 수정:
```python
"""권한 관리 에이전트 (ADR-0029). NL 지시 → 구조화 파싱 → 화이트리스트 검증 →
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v
```

기대 결과: 전체 `PASSED`

- [ ] **Step 5: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/tools/permission_tool.py backend/tests/app/graph/tools/test_permission_tool.py
git commit -m "refactor: PermissionToolHandler → PermissionAgent 개명"
```

---

### Task 5: `registry.py` 일괄 반영 + 전체 테스트

**Files:**
- Modify: `app/graph/tools/registry.py`

- [ ] **Step 1: registry.py 전체를 아래로 교체**

```python
"""도구 레지스트리 (ADR-0023). 도구명 → 에이전트, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 에이전트를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from app.graph.tools.audit_history_tool import AuditAgent
from app.graph.tools.sql_tool import SqlAgent
from app.graph.tools.permission_tool import PermissionAgent


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolAgent
    tool_defs: list[BaseTool]   # bind_tools용


def build_tool_registry(
    *, llm: LLMClient, sql_pool, sql_rw_pool=None, fga_client: FGAClient, app_pool=None
) -> ToolRegistry:
    sql = SqlAgent(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool)
    permission = PermissionAgent(
        llm=llm, fga_client=fga_client, validator=PermissionValidator.from_config()
    )
    audit = AuditAgent(fga_client=fga_client, app_pool=app_pool)
    handlers = {sql.name: sql, permission.name: permission, audit.name: audit}
    tool_defs = [sql.tool, permission.tool, audit.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)
```

- [ ] **Step 2: 전체 도구 관련 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/ -v
```

기대 결과: 전체 `PASSED` (test_registry.py 포함)

- [ ] **Step 3: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/tools/registry.py
git commit -m "refactor: registry *ToolHandler → *Agent 개명 반영"
```

---

### Task 6: `PermissionAgent`에 `query` 액션 추가

**Files:**
- Modify: `app/graph/prompts.py` (PERMISSION_PARSE_PROMPT)
- Modify: `app/graph/tools/permission_tool.py`
- Modify: `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: 신규 테스트 추가 (실패 상태로 시작)**

`tests/app/graph/tools/test_permission_tool.py` 파일 끝에 아래를 추가:

```python
@pytest.mark.asyncio
async def test_execute_query_self_returns_snapshot():
    """본인 조회: caller == target → 관리자 확인 없이 FGA 3종 조회."""
    fga = MagicMock()
    fga.user_departments = AsyncMock(return_value=["engineering"])
    fga.user_roles = AsyncMock(return_value=["admin"])
    fga.get_readable_folders = AsyncMock(return_value=["/engineering/specs"])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-alice user-alice", "RISK_SELECT")
    assert "user-alice" in result
    assert "engineering" in result
    assert "/engineering/specs" in result
    fga.check.assert_not_called()


@pytest.mark.asyncio
async def test_execute_query_other_as_admin_succeeds():
    """타인 조회: caller != target, admin → 성공."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["product"])
    fga.user_roles = AsyncMock(return_value=[])
    fga.get_readable_folders = AsyncMock(return_value=[])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query admin-user user-bob", "RISK_SELECT")
    fga.check.assert_awaited_once_with("user:admin-user", "member", "capability:admin")
    assert "user-bob" in result


@pytest.mark.asyncio
async def test_execute_query_other_as_non_admin_denied():
    """타인 조회: caller != target, 비관리자 → 거부 메시지."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=False)
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-alice user-bob", "RISK_SELECT")
    assert "권한 없음" in result
    fga.user_departments.assert_not_called()


def test_plan_query_self_returns_risk_select():
    """query 파싱 → RISK_SELECT, planned_action 형식 확인."""
    from core.sql.risk import RISK_SELECT
    agent = PermissionAgent(
        llm=_llm('{"action":"query","target_user_id":null}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = agent.plan({"instruction": "내 권한 알려줘", "__caller_id": "user-alice"})
    assert risk == RISK_SELECT
    assert planned == "query user-alice user-alice"


def test_plan_query_other_returns_risk_select():
    """타인 query도 plan 단계에선 RISK_SELECT (관리자 확인은 execute에서)."""
    from core.sql.risk import RISK_SELECT
    agent = PermissionAgent(
        llm=_llm('{"action":"query","target_user_id":"user-bob"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = agent.plan({"instruction": "bob 권한 알려줘", "__caller_id": "user-alice"})
    assert risk == RISK_SELECT
    assert planned == "query user-alice user-bob"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -k "query" -v
```

기대 결과: 5개 테스트 모두 `FAILED` (NotImplemented 또는 AttributeError)

- [ ] **Step 3: `PERMISSION_PARSE_PROMPT` 수정**

`app/graph/prompts.py` 의 `PERMISSION_PARSE_PROMPT` 전체를 아래로 교체:

```python
PERMISSION_PARSE_PROMPT = """\
다음 권한 관리 지시를 JSON으로 변환하라.

알려진 식별자(반드시 이 정확한 id를 사용):
{known_ids}

규칙:
- action: "grant"(부여), "revoke"(회수), "query"(조회)
- query 시: {{"action":"query","target_user_id":"<유저id 또는 null>"}}
  target_user_id가 없으면 null (본인 조회)
- grant/revoke 시:
  부서 멤버십: subject="user:<유저id>", relation="member", object="department:<부서>"
  폴더 부서 접근권: subject="department:<부서>#member", relation="dept_viewer", object="folder:<경로>"
  SQL 권한: subject="user:<유저id>" 또는 "department:<부서>#member",
    relation 은 allow_select/justify_select/allow_bulk_select/justify_bulk_select/allow_update_delete/justify_update_delete/allow_ddl/justify_ddl 중 하나, object="capability:sql"

grant/revoke 키: action, subject, relation, object 네 개.
query 키: action, target_user_id 두 개.
JSON 객체만 출력(설명·코드펜스 금지).

지시: {instruction}

JSON:"""
```

- [ ] **Step 4: `PermissionAgent.plan()` query 분기 추가**

`app/graph/tools/permission_tool.py` 의 `plan()` 메서드 전체를 아래로 교체:

```python
    def plan(self, args: dict) -> tuple[str, str]:
        instruction = single_text_arg(args, prefer="instruction")
        caller = args.get("__caller_id", "")
        prompt = (
            PERMISSION_PARSE_PROMPT
            .replace("{known_ids}", self._validator.catalog_text())
            .replace("{instruction}", instruction)
        )
        raw = self._llm.complete(prompt)
        try:
            parsed = json.loads(strip_code_fence(raw))
        except Exception:
            return "권한 동작 파싱 실패", RISK_DENY
        if not isinstance(parsed, dict):
            return "권한 동작 파싱 실패", RISK_DENY

        action = parsed.get("action")
        if action == "query":
            target = parsed.get("target_user_id") or caller
            return f"query {caller} {target}", RISK_SELECT

        validated = self._validator.validate(parsed)
        if validated is None:
            return "검증 실패: 유효하지 않은 권한 동작", RISK_DENY
        subject, relation, object_, action = validated
        return f"{action} {subject} {relation} {object_}", RISK_GRANT
```

상단 import에 `RISK_SELECT` 추가:

```python
from core.sql.risk import RISK_DENY, RISK_SELECT
```

- [ ] **Step 5: `PermissionAgent.execute()` query 분기 추가**

`app/graph/tools/permission_tool.py` 에 포맷 함수와 `execute()` query 분기를 추가.

클래스 외부(파일 끝)에 포맷 함수 추가:

```python
def _format_permission_snapshot(uid: str, departments: list, roles: list, folders: list) -> str:
    dept_text = ", ".join(departments) if departments else "(없음)"
    role_text = ", ".join(roles) if roles else "(없음)"
    if folders:
        folder_lines = "\n".join(f"  - {f}" for f in folders)
        folder_text = f"{len(folders)}개:\n{folder_lines}"
    else:
        folder_text = "(없음)"
    return (
        f"사용자: {uid}\n"
        f"소속 부서: {dept_text}\n"
        f"역할(role): {role_text}\n"
        f"접근 가능 폴더 {folder_text}"
    )
```

`execute()` 메서드 전체를 아래로 교체:

```python
    async def execute(self, planned_action: str, risk: str) -> str:
        if planned_action.startswith("query "):
            parts = planned_action.split(" ", 2)
            if len(parts) != 3:
                return "권한 조회 오류: 잘못된 동작 형식"
            _, caller, target = parts
            if target != caller:
                try:
                    admin_ok = await self._fga.check(f"user:{caller}", "member", "capability:admin")
                except Exception:
                    return "권한 없음: 관리자 확인 실패"
                if not admin_ok:
                    return "권한 없음: 타인 조회는 관리자만 가능합니다."
            try:
                departments = await self._fga.user_departments(target)
                roles = await self._fga.user_roles(target)
                folders = await self._fga.get_readable_folders(target)
            except Exception as exc:
                return f"권한 조회 오류: {type(exc).__name__}"
            return _format_permission_snapshot(target, departments, roles, folders)

        parts = planned_action.split(" ")
        if len(parts) != 4:
            return "권한 실행 오류: 잘못된 동작 형식"
        action, subject, relation, object_ = parts
        try:
            if action == "grant":
                await self._fga.grant_tuple(subject, relation, object_)
            elif action == "revoke":
                await self._fga.revoke_tuple(subject, relation, object_)
            else:
                return "권한 실행 오류: 알 수 없는 action"
            return f"완료: {planned_action}"
        except Exception as exc:
            return f"권한 실행 오류: {type(exc).__name__}"
```

- [ ] **Step 6: 도구 description 수정**

`permission_tool.py` 의 `_DESCRIPTION` 첫 줄을 수정:

```python
_DESCRIPTION = (
    "사내 접근 권한을 조회·부여·회수한다: 부서 멤버십, 폴더 접근권, SQL 실행 권한 등급. "
    "예: '내 접근 가능한 폴더 알려줘', 'alice 권한 조회', '앨리스를 엔지니어링 부서에 추가'. "
    "직원 연봉·매출 같은 테이블 데이터 수정은 이 도구가 아니라 query_business_data를 쓴다. "
    "instruction 인자에 한국어 자연어 지시를 그대로 넣는다."
)
```

- [ ] **Step 7: query 테스트 통과 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v
```

기대 결과: 전체 `PASSED` (기존 6개 + 신규 5개)

- [ ] **Step 8: 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/app/graph/prompts.py backend/app/graph/tools/permission_tool.py backend/tests/app/graph/tools/test_permission_tool.py
git commit -m "feat(permission): PermissionAgent query 액션 추가 — 권한 조회 기능"
```

---

### Task 7: 전체 회귀 테스트

- [ ] **Step 1: 전체 테스트 수행**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m pytest -v
```

기대 결과: 전체 `PASSED`, 실패 0건

- [ ] **Step 2: 실패 시 원인 파악 후 수정**

실패 테스트가 있으면 에러 메시지를 확인하고 해당 Task를 재작업한다.
(`ImportError`면 import 누락, `AttributeError`면 메서드 시그니처 불일치)

- [ ] **Step 3: ADR 작성**

`docs/superpowers/decisions/ADR-0041-permission-agent-rename-query.md` 생성:

```markdown
# ADR-0041: ToolHandler → ToolAgent 개명 + PermissionAgent query 액션

> **Status**: 🟢 적용완료

**Date**: 2026-06-04

## Context
`*ToolHandler` 클래스들이 `plan() → gate → execute()` ReAct 루프를 직접 구현하는 에이전트임에도
`Handler` 접미사로 개념 불일치가 발생했다. 동시에 권한 조회("내 접근 폴더 알려줘") 기능이 없어
사용자가 챗봇을 통해 자신의 권한을 확인할 수 없었다.

## Decision
1. `ToolHandler` Protocol → `ToolAgent`, `SqlToolHandler` → `SqlAgent`,
   `AuditHistoryToolHandler` → `AuditAgent`, `PermissionToolHandler` → `PermissionAgent` 개명.
2. `PermissionAgent`에 `query` 액션 추가: `plan()`은 RISK_SELECT 반환(게이트 자동 승인),
   `execute()`에서 본인/관리자 검증 후 FGA 3종(부서·역할·폴더) 조회 결과 반환.

## Consequences
- 외부 도구명(`manage_permission`)·FGA 스키마·DB 스키마 불변.
- 기존 grant/revoke 동작 불변.
- 일반 사용자: 본인 권한 조회 가능. 관리자: 타인 권한 조회 가능.

## 관련 ADR
- [ADR-0023](ADR-0023-tool-call-agentic-loop.md) — ReAct 루프 및 ToolAgent 패턴 정의
- [ADR-0029](ADR-0029-permission-management-tool.md) — PermissionAgent 원형
- [ADR-0033](ADR-0033-terminology-naming-deadcode-cleanup.md) — 캡슐화 기반 명명 표준
```

- [ ] **Step 4: ADR 인덱스 갱신**

```bash
cd /Users/acacian/vscode/company-rag/backend && .venv/bin/python -m scripts.gen_adr_index
```

- [ ] **Step 5: 최종 커밋**

```bash
cd /Users/acacian/vscode/company-rag && git add backend/docs/superpowers/decisions/ADR-0041-permission-agent-rename-query.md backend/docs/superpowers/decisions/README.md
git commit -m "docs: ADR-0041 ToolAgent 개명 + PermissionAgent query 액션"
```

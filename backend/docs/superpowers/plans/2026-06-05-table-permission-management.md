# Table Permission Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `manage_permission` 도구를 통해 테이블 접근권(`dept_viewer on table:*`)을 grant/revoke할 수 있게 하고, 권한 스냅샷에 테이블 접근 현황을 노출한다.

**Architecture:** FGA 모델의 `type table`을 `dept_viewer` 단일 relation으로 단순화하고 (폴더 `dept_viewer`와 동형), `PermissionValidator`에 테이블 케이스를 추가하며, `FGAClient`에 `user_accessible_tables()` 조회 메서드를 추가한다. 게이트는 기존 `gate_table_access()`의 체크 relation만 `can_access` → `dept_viewer`로 변경한다.

**Tech Stack:** Python 3.11, OpenFGA (openfga_sdk), pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-06-05-table-permission-management-design.md`

---

## File Map

| 파일 | 변경 종류 | 내용 |
|------|-----------|------|
| `fga/model.fga` | 수정 | `type table` — `dept_viewer` 단일 relation |
| `scripts/seed_fga.py` | 수정 | `_TABLE_GRANTS` relation: `can_access` → `dept_viewer` |
| `core/sql/gate.py` | 수정 | `gate_table_access()` 체크 relation: `dept_viewer` |
| `core/fga/permission_validator.py` | 수정 | `_KNOWN_TABLES` 상수 + `dept_viewer on table:*` 케이스 |
| `core/fga/client.py` | 수정 | `user_accessible_tables()` 메서드 추가 |
| `app/graph/tools/permission_tool.py` | 수정 | 스냅샷에 테이블 섹션 추가 |
| `tests/core/sql/test_gate.py` | 수정 | `_table_checker` → `dept_viewer` + 신규 케이스 |
| `tests/core/fga/test_permission_validator.py` | 수정 | 테이블 `dept_viewer` 케이스 추가 |
| `tests/app/graph/tools/test_permission_tool.py` | 수정 | 스냅샷 테이블 섹션 + `user_accessible_tables` mock |

---

## Task 1: gate_table_access() — `dept_viewer`로 체크 relation 변경

**Files:**
- Modify: `core/sql/gate.py:67-83`
- Test: `tests/core/sql/test_gate.py:101-138`

- [ ] **Step 1: 기존 테이블 게이트 테스트의 checker를 `dept_viewer`로 변경**

`tests/core/sql/test_gate.py`의 `_table_checker` 함수를 수정한다:

```python
def _table_checker(granted: set):
    """granted = dept_viewer 보유 table 객체 집합(예: {"table:employees"})."""
    async def check(user, relation, object_):
        return relation == "dept_viewer" and object_ in granted
    return check
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd /Users/acacian/vscode/company-rag/backend
.venv/bin/python -m pytest tests/core/sql/test_gate.py::test_table_access_all_present tests/core/sql/test_gate.py::test_table_access_missing_one_denies -v
```

Expected: FAIL (`can_access` 체크로 인해 `dept_viewer` checker가 False 반환)

- [ ] **Step 3: `gate_table_access()` 체크 relation 변경**

`core/sql/gate.py`의 `gate_table_access()` 함수에서 relation을 변경한다:

```python
async def gate_table_access(
    check: Callable[[str, str, str], Awaitable[bool]],
    user_id: str,
    tables: set[str],
) -> tuple[bool, str]:
    """테이블별 접근 게이트 (ADR-0047) — 참조 테이블 전부의 dept_viewer를 AND로 확인.

    위험도 게이트(gate_decision)와 직교한다: "어떤 작업이냐"는 gate_decision이,
    "어느 테이블이냐"는 여기서 본다. 호출자(tool_gate_node)가 둘을 AND로 합성한다.
    dept_viewer 튜플이 없는 테이블(미부여·미지)은 자연히 실패 → fail-closed.
    참조 테이블이 없으면(빈 집합) 통과한다(예: SELECT 1).
    """
    user = f"user:{user_id}"
    for table in sorted(tables):
        if not await check(user, "dept_viewer", f"table:{table}"):
            return False, f"table:{table} dept_viewer 미보유 → DENY"
    return True, "참조 테이블 dept_viewer 전부 보유 → 통과"
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
.venv/bin/python -m pytest tests/core/sql/test_gate.py -v
```

Expected: 전체 PASS (기존 `gate_decision` 테스트 + 수정된 테이블 게이트 테스트 모두)

- [ ] **Step 5: 커밋**

```bash
git add core/sql/gate.py tests/core/sql/test_gate.py
git commit -m "fix(gate): table gate 체크 relation can_access → dept_viewer"
```

---

## Task 2: FGA 모델 + seed 변경

**Files:**
- Modify: `fga/model.fga:47-51`
- Modify: `scripts/seed_fga.py:52-62`

- [ ] **Step 1: `fga/model.fga`의 `type table` 변경**

`fga/model.fga` 파일에서 `type table` 블록을 교체한다:

```
# 업무 DB 테이블 단위 접근권 (ADR-0047). table:employees / table:sales 인스턴스가 사용.
# 위험도 게이트(capability:sql)와 직교 — "어느 테이블이냐"만 본다.
# dept_viewer: 폴더와 동형 — user·부서·역할 모두 grant 가능. can_access 레이어 없음.
type table
  relations
    define dept_viewer: [user, department#member, role#member]
```

- [ ] **Step 2: `scripts/seed_fga.py`의 `_TABLE_GRANTS` relation 변경**

`_TABLE_GRANTS` 리스트의 모든 `"can_access"` → `"dept_viewer"` 로 변경한다:

```python
_TABLE_GRANTS = [
    {"user": "role:c_level#member",       "relation": "dept_viewer", "object": "table:employees"},
    {"user": "role:c_level#member",       "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:인사팀#member",  "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:재무팀#member",  "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:재무팀#member",  "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:개발팀#member",  "relation": "dept_viewer", "object": "table:employees"},
    {"user": "department:개발팀#member",  "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:영업팀#member",  "relation": "dept_viewer", "object": "table:sales"},
    {"user": "department:제품팀#member",  "relation": "dept_viewer", "object": "table:sales"},
]
```

- [ ] **Step 3: seed 스크립트 문법 확인**

```bash
.venv/bin/python -c "import scripts.seed_fga; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add fga/model.fga scripts/seed_fga.py
git commit -m "feat(fga): type table dept_viewer 단일 relation으로 단순화 + seed 갱신"
```

---

## Task 3: PermissionValidator — 테이블 `dept_viewer` 케이스 추가

**Files:**
- Modify: `core/fga/permission_validator.py`
- Test: `tests/core/fga/test_permission_validator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/core/fga/test_permission_validator.py` 파일 끝에 아래 테스트를 추가한다:

```python
# ── 테이블 dept_viewer 케이스 (ADR-0047, dept_viewer 단일 relation) ──────────────

def _table_validator():
    return PermissionValidator(
        user_ids={"user-joohwan", "user-minjun"},
        departments={"개발팀", "영업팀"},
        folders={"/company"},
    )


def test_valid_table_dept_viewer_grant_to_department():
    v = _table_validator()
    tup = v.validate({
        "action": "grant",
        "subject": "department:개발팀#member",
        "relation": "dept_viewer",
        "object": "table:employees",
    })
    assert tup == ("department:개발팀#member", "dept_viewer", "table:employees", "grant")


def test_valid_table_dept_viewer_grant_to_user():
    v = _table_validator()
    tup = v.validate({
        "action": "grant",
        "subject": "user:user-joohwan",
        "relation": "dept_viewer",
        "object": "table:sales",
    })
    assert tup == ("user:user-joohwan", "dept_viewer", "table:sales", "grant")


def test_valid_table_dept_viewer_revoke():
    v = _table_validator()
    tup = v.validate({
        "action": "revoke",
        "subject": "department:영업팀#member",
        "relation": "dept_viewer",
        "object": "table:sales",
    })
    assert tup == ("department:영업팀#member", "dept_viewer", "table:sales", "revoke")


def test_reject_table_dept_viewer_unknown_table():
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "department:개발팀#member",
        "relation": "dept_viewer",
        "object": "table:secret_data",
    }) is None


def test_reject_table_dept_viewer_unknown_department():
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "department:마케팅팀#member",
        "relation": "dept_viewer",
        "object": "table:employees",
    }) is None


def test_reject_table_can_access_direct_grant():
    # can_access는 더 이상 grant 대상이 아님 — dept_viewer만 허용
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "user:user-joohwan",
        "relation": "can_access",
        "object": "table:employees",
    }) is None


def test_catalog_text_contains_table_names():
    v = _table_validator()
    text = v.catalog_text()
    assert "employees" in text
    assert "sales" in text
    assert "테이블" in text
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py::test_valid_table_dept_viewer_grant_to_department -v
```

Expected: FAIL (`dept_viewer on table:*` 케이스 미구현)

- [ ] **Step 3: `_KNOWN_TABLES` 상수 추가**

`core/fga/permission_validator.py` 파일 상단 `_CAPABILITY_RELATIONS` 상수 아래에 추가한다:

```python
# 접근 권한 관리 대상 테이블 화이트리스트 (ADR-0047, seed_fga._TABLE_GRANTS와 동기화).
# DB 스키마가 고정된 환경에서 코드 상수로 관리. 새 테이블 추가 시 여기에 추가 후 seed 재실행.
_KNOWN_TABLES = {"employees", "sales"}
```

- [ ] **Step 4: `validate()`에 `dept_viewer on table:*` 케이스 추가**

`core/fga/permission_validator.py`의 `validate()` 메서드에서 `elif relation in _CAPABILITY_RELATIONS:` 블록 앞에 새 케이스를 삽입한다:

```python
        elif relation == "dept_viewer" and object_.startswith("table:"):
            table = self._strip(object_, "table:")
            if table not in _KNOWN_TABLES:
                return None
            resolved = self._resolve_user(subject)
            if resolved is not None:
                subject = resolved
            else:
                dept = self._strip(subject, "department:")
                if dept is not None and dept.endswith("#member"):
                    dept = dept[: -len("#member")]
                else:
                    return None
                if dept not in self._departments:
                    return None
```

- [ ] **Step 5: `catalog_text()`에 테이블 목록 추가**

`core/fga/permission_validator.py`의 `catalog_text()` 메서드를 교체한다:

```python
    def catalog_text(self) -> str:
        """LLM 파싱 프롬프트에 주입할 알려진 id 목록(정확한 id 유도용)."""
        users = ", ".join(sorted(self._user_ids))
        depts = ", ".join(sorted(self._departments))
        folders = ", ".join(sorted(self._folders))
        tables = ", ".join(sorted(_KNOWN_TABLES))
        return f"유저: {users}\n부서: {depts}\n폴더: {folders}\n테이블: {tables}"
```

- [ ] **Step 6: 전체 validator 테스트 통과 확인**

```bash
.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py -v
```

Expected: 전체 PASS

- [ ] **Step 7: 커밋**

```bash
git add core/fga/permission_validator.py tests/core/fga/test_permission_validator.py
git commit -m "feat(validator): 테이블 dept_viewer grant/revoke 검증 + 카탈로그 테이블 목록 추가"
```

---

## Task 4: FGAClient — `user_accessible_tables()` 추가

**Files:**
- Modify: `core/fga/client.py`
- Test: `tests/core/fga/test_client.py`

- [ ] **Step 1: 테스트 파일 확인**

```bash
.venv/bin/python -m pytest tests/core/fga/test_client.py -v
```

현재 통과하는 테스트 목록 확인.

- [ ] **Step 2: 실패 테스트 작성**

`tests/core/fga/test_client.py` 파일 끝에 추가한다:

```python
# ── user_accessible_tables ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_accessible_tables_returns_permitted_only():
    """dept_viewer 보유 테이블만 반환, 미보유는 제외."""
    from unittest.mock import AsyncMock, patch
    from core.fga.client import FGAClient
    from core.fga.models import FGAConfig
    from core.fga.memory_cache import MemoryCache

    client = FGAClient(
        config=FGAConfig(api_url="http://localhost", store_id="test", api_key=""),
        cache=MemoryCache(),
    )

    # employees → True, sales → False
    async def fake_check(user, relation, object_):
        return object_ == "table:employees" and relation == "dept_viewer"

    with patch.object(client, "check", side_effect=fake_check):
        result = await client.user_accessible_tables("user-joohwan")

    assert result == ["employees"]


@pytest.mark.asyncio
async def test_user_accessible_tables_all_permitted():
    """모든 테이블 dept_viewer 보유 시 전체 반환."""
    from unittest.mock import patch
    from core.fga.client import FGAClient
    from core.fga.models import FGAConfig
    from core.fga.memory_cache import MemoryCache

    client = FGAClient(
        config=FGAConfig(api_url="http://localhost", store_id="test", api_key=""),
        cache=MemoryCache(),
    )

    async def fake_check(user, relation, object_):
        return relation == "dept_viewer"

    with patch.object(client, "check", side_effect=fake_check):
        result = await client.user_accessible_tables("user-joohwan")

    assert sorted(result) == ["employees", "sales"]


@pytest.mark.asyncio
async def test_user_accessible_tables_none_permitted():
    """dept_viewer 미보유 시 빈 리스트 반환."""
    from unittest.mock import patch
    from core.fga.client import FGAClient
    from core.fga.models import FGAConfig
    from core.fga.memory_cache import MemoryCache

    client = FGAClient(
        config=FGAConfig(api_url="http://localhost", store_id="test", api_key=""),
        cache=MemoryCache(),
    )

    async def fake_check(user, relation, object_):
        return False

    with patch.object(client, "check", side_effect=fake_check):
        result = await client.user_accessible_tables("user-joohwan")

    assert result == []
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
.venv/bin/python -m pytest tests/core/fga/test_client.py::test_user_accessible_tables_returns_permitted_only -v
```

Expected: FAIL (`user_accessible_tables` 미정의)

- [ ] **Step 4: `user_accessible_tables()` 구현**

`core/fga/client.py`의 `user_departments()` 메서드 아래에 추가한다:

```python
    async def user_accessible_tables(self, user_id: str) -> list[str]:
        """사용자가 dept_viewer 권한을 가진 테이블 목록 (ADR-0047).

        _KNOWN_TABLES 각각에 대해 check를 호출하므로 N회 FGA round-trip 발생.
        테이블 수가 적어(현재 2개) 성능 문제 없음.
        """
        from core.fga.permission_validator import _KNOWN_TABLES
        result = []
        for table in sorted(_KNOWN_TABLES):
            if await self.check(f"user:{user_id}", "dept_viewer", f"table:{table}"):
                result.append(table)
        return result
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
.venv/bin/python -m pytest tests/core/fga/test_client.py -v
```

Expected: 전체 PASS

- [ ] **Step 6: 커밋**

```bash
git add core/fga/client.py tests/core/fga/test_client.py
git commit -m "feat(client): user_accessible_tables() 메서드 추가"
```

---

## Task 5: permission_tool — 스냅샷에 테이블 접근 섹션 추가

**Files:**
- Modify: `app/graph/tools/permission_tool.py`
- Test: `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: `_format_permission_snapshot` 테이블 섹션 실패 테스트 작성**

`tests/app/graph/tools/test_permission_tool.py` 파일 끝에 추가한다:

```python
def test_format_snapshot_renders_table_section():
    """스냅샷에 '### 접근 가능 테이블' 섹션이 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", ["개발팀"], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용")],
        tables=["employees", "sales"],
    )
    assert "### 접근 가능 테이블" in out
    assert "employees" in out
    assert "sales" in out


def test_format_snapshot_no_tables_shows_none():
    """테이블 접근권 없으면 '(없음)' 표시."""
    out = _format_permission_snapshot(
        "user-alice", [], [], [],
        [("SELECT", "즉시 허용")],
        tables=[],
    )
    assert "### 접근 가능 테이블" in out
    assert "(없음)" in out


@pytest.mark.asyncio
async def test_execute_query_includes_table_access():
    """query execute 결과에 테이블 접근 정보가 포함된다."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["개발팀"])
    fga.user_roles = AsyncMock(return_value=[])
    fga.get_readable_folders = AsyncMock(return_value=[])
    fga.user_accessible_tables = AsyncMock(return_value=["employees", "sales"])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-joohwan", "RISK_SELECT")
    fga.user_accessible_tables.assert_awaited_once_with("user-joohwan")
    assert "employees" in result
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py::test_format_snapshot_renders_table_section -v
```

Expected: FAIL (`_format_permission_snapshot`에 `tables` 파라미터 없음)

- [ ] **Step 3: `_format_permission_snapshot()` 시그니처 및 구현 변경**

`app/graph/tools/permission_tool.py`의 `_format_permission_snapshot` 함수를 교체한다:

```python
def _format_permission_snapshot(
    uid: str,
    departments: list,
    roles: list,
    folders: list,
    capabilities: list,
    tables: list | None = None,
) -> str:
    dept_text = ", ".join(departments) if departments else "(없음)"
    role_text = ", ".join(roles) if roles else "(없음)"

    if folders:
        folder_lines = "\n".join(f"- {f}" for f in folders)
    else:
        folder_lines = "(없음)"

    if tables:
        table_text = ", ".join(tables)
    else:
        table_text = "(없음)"

    decision_icon = {
        "즉시 허용": "✅",
        "사유 기재 후 허용": "⚠️",
        "불가": "❌",
    }
    cap_rows = "\n".join(
        f"| {label} | {decision_icon.get(decision, '')} {decision} |"
        for label, decision in capabilities
    )

    return (
        f"## 권한 스냅샷\n\n"
        f"**사용자**: {uid}\n"
        f"**소속 부서**: {dept_text}\n"
        f"**역할(role)**: {role_text}\n\n"
        f"### 접근 가능 폴더\n{folder_lines}\n\n"
        f"### 접근 가능 테이블\n{table_text}\n\n"
        f"### SQL/관리 권한\n"
        f"| 작업 | 허용 여부 |\n"
        f"|------|----------|\n"
        f"{cap_rows}"
    )
```

- [ ] **Step 4: 기존 query 테스트에 `user_accessible_tables` mock 추가**

`tests/app/graph/tools/test_permission_tool.py`에서 `execute()` query 경로를 통과하는 두 테스트에 mock을 추가한다. `user_accessible_tables`가 `AsyncMock` 없이 호출되면 `await` 실패.

`test_execute_query_self_returns_snapshot` 수정:
```python
async def test_execute_query_self_returns_snapshot():
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["개발팀"])
    fga.user_roles = AsyncMock(return_value=["admin"])
    fga.get_readable_folders = AsyncMock(return_value=["/engineering/specs"])
    fga.user_accessible_tables = AsyncMock(return_value=["employees"])  # 추가
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-joohwan", "RISK_SELECT")
    assert "user-joohwan" in result
    assert "개발팀" in result
    assert "/engineering/specs" in result
    assert "SQL/관리 권한" in result
```

`test_execute_query_other_as_admin_succeeds` 수정:
```python
async def test_execute_query_other_as_admin_succeeds():
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["제품팀"])
    fga.user_roles = AsyncMock(return_value=[])
    fga.get_readable_folders = AsyncMock(return_value=[])
    fga.user_accessible_tables = AsyncMock(return_value=[])  # 추가
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query admin-user user-minjun", "RISK_SELECT")
    fga.check.assert_any_await("user:admin-user", "justify_grant", "capability:admin")
    assert "user-minjun" in result
```

- [ ] **Step 5: `execute()` query 분기에 `user_accessible_tables()` 추가**

`app/graph/tools/permission_tool.py`의 `execute()` 메서드 query 분기에서 `capabilities` 조회 다음에 한 줄 추가하고, `_format_permission_snapshot` 호출에 `tables` 인자를 추가한다:

```python
        try:
            departments = await self._fga.user_departments(target)
            roles = await self._fga.user_roles(target)
            folders = await self._fga.get_readable_folders(target)
            capabilities = await _resolve_capabilities(self._fga.check, target)
            tables = await self._fga.user_accessible_tables(target)
        except Exception as exc:
            return f"권한 조회 오류: {type(exc).__name__}"
        return _format_permission_snapshot(target, departments, roles, folders, capabilities, tables)
```

- [ ] **Step 6: 기존 스냅샷 테스트 통과 확인**

기존 `test_format_snapshot_*` 테스트는 `tables` 파라미터를 넘기지 않는다. `tables=None`이 기본값이므로 그대로 통과해야 한다.

```bash
.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v
```

Expected: 전체 PASS (기존 테스트 + 신규 테스트)

- [ ] **Step 7: 전체 테스트 스위트 회귀 확인**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: 전체 PASS

- [ ] **Step 8: 커밋**

```bash
git add app/graph/tools/permission_tool.py tests/app/graph/tools/test_permission_tool.py
git commit -m "feat(permission-tool): 권한 스냅샷에 테이블 접근 섹션 추가"
```

---

## Task 6: ADR 작성 + 마이그레이션 안내

**Files:**
- Create: `docs/superpowers/decisions/ADR-0050-table-dept-viewer-model.md`

- [ ] **Step 1: ADR 작성**

`docs/superpowers/decisions/ADR-0050-table-dept-viewer-model.md` 파일을 생성한다:

```markdown
# ADR-0050: type table dept_viewer 단일 relation 모델

> **Status**: 🟢 적용완료

**Date**: 2026-06-05
**Context**: ADR-0047에서 정의된 `type table`의 `can_access`를 `dept_viewer` 단일 relation으로 대체해 폴더 권한 모델과 동형화한다.

## Options
| 선택지 | 트레이드오프 |
|--------|------------|
| A. `can_access` 유지 (flat) | 단순하지만 폴더와 이질적. `manage_permission` 파싱 코드 재사용 불가 |
| B. `dept_viewer` 단일 relation | 폴더 동형, manage_permission 파싱 재사용, can_access 레이어 제거 |

## Decision
**선택: B — `dept_viewer` 단일 relation**

## Rationale
DB 스키마가 고정된 환경에서 테이블 목록은 코드 상수(`_KNOWN_TABLES`)로 관리하고,
grant/revoke 인터페이스를 폴더의 `dept_viewer` 패턴과 동형화한다.
`manage_permission` 도구의 파싱·검증 로직이 재사용되고, `gate_table_access()`는
체크 relation 한 줄만 변경된다.
```

- [ ] **Step 2: ADR 인덱스 갱신**

```bash
.venv/bin/python -m scripts.gen_adr_index
```

Expected: `docs/superpowers/decisions/README.md` 갱신

- [ ] **Step 3: FGA store 마이그레이션 안내 출력**

기존 `can_access` 튜플이 FGA store에 남아 있으면 stale이 된다. 개발 환경에서 정합화:

```bash
.venv/bin/python -m scripts.seed_fga --prune
```

Expected: 기존 `can_access` 튜플 삭제 + 신규 `dept_viewer` 튜플 추가 메시지 출력

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/decisions/ADR-0050-table-dept-viewer-model.md docs/superpowers/decisions/README.md
git commit -m "docs(adr): ADR-0050 type table dept_viewer 단일 relation 모델"
```

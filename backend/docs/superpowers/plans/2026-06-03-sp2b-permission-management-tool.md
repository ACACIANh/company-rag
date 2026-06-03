# SP2b: 권한 관리 도구 manage_permission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tool_call 에이전트 루프에 `manage_permission` 도구를 등록해, 권한자가 자연어로 부서 멤버십·폴더 접근권·SQL capability를 grant/revoke하고, 그 행위가 capability:admin 게이트(JUSTIFY)·HITL·감사를 거치게 한다.

**Architecture:** SQL 도구와 동형 — NL 입력을 `plan`에서 LLM이 `{action, subject, relation, object}`로 파싱하고 화이트리스트로 검증해 `RISK_GRANT`/`RISK_DENY`를 낸다. `gate_decision`을 risk별 `(객체, relation 베이스)` 매핑으로 일반화해 `RISK_GRANT`를 `capability:admin`의 `allow_grant`/`justify_grant`로 게이트한다. `execute`는 검증된 튜플을 FGA write/delete한다. HITL은 SP1 흐름(도구 불가지)을 그대로 재사용.

**Tech Stack:** OpenFGA(openfga_sdk), LangChain Tool, Python 3.11, pytest. 설계: `docs/superpowers/decisions/ADR-0029-permission-management-tool.md`

---

## File Structure

- `core/sql/gate.py` (수정) — `_RISK_GATE` 일반화 + `RISK_GRANT`. SQL·grant 게이트의 단일 출처.
- `fga/model.fga` + `fga/model.json` (수정/재생성) — `capability` 타입에 `allow_grant`/`justify_grant`.
- `core/fga/client.py` (수정) — 범용 `grant_tuple`/`revoke_tuple`.
- `core/fga/permission_validator.py` (생성) — 파싱 결과 화이트리스트 검증 + 카탈로그 텍스트. LangGraph 불가지.
- `app/graph/prompts.py` (수정) — `PERMISSION_PARSE_PROMPT`.
- `app/graph/tools/permission_tool.py` (생성) — `PermissionToolHandler`(plan/execute).
- `app/graph/tools/registry.py` (수정) — `manage_permission` 등록(fga_client·validator 주입).
- `app/graph/builder.py` (수정) — `build_tool_registry`에 fga_client 전달.
- `scripts/seed_fga.py` (수정) — `capability:admin` `justify_grant` 시드.
- 각 `tests/...` — 단위·통합 테스트.

---

## Task 0: 브랜치 생성

- [ ] **Step 1: feat 브랜치 생성**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend && git checkout -b feat/sp2b-permission-tool
```
Expected: `Switched to a new branch 'feat/sp2b-permission-tool'`

> 작업 디렉토리는 항상 `backend/`. 인터프리터 `.venv/bin/python`. OpenFGA·Postgres 컨테이너 가동 중.

---

## Task 1: gate.py 일반화 — RISK_GRANT + capability:admin

**Files:**
- Modify: `core/sql/gate.py`
- Modify: `tests/core/sql/test_gate.py`

- [ ] **Step 1: 테스트 갱신 (test_gate.py)**

기존 `tests/core/sql/test_gate.py`는 `CAPABILITY_OBJECT`를 import하고 checker가 `object_ == CAPABILITY_OBJECT`를 단언한다. 일반화 후 객체가 2종(capability:sql/admin)이므로 checker를 `(relation, object_)` 쌍으로 판정하도록 바꾸고 RISK_GRANT 케이스를 추가한다. 파일 전체를 다음으로 교체:
```python
import pytest

from core.sql.gate import (
    gate_decision,
    RISK_GRANT,
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_JUSTIFY_AND_APPROVE,
)
from core.sql.risk import (
    RISK_SELECT,
    RISK_BULK_SELECT,
    RISK_UPDATE_DELETE,
    RISK_DDL,
    RISK_DENY,
)

# 시드 기본부여를 user 단위로 푼 상태(ADR-0028/0029). OpenFGA Check가 상속을 풀어
# 반환하는 결과를 (relation, object) 쌍 set으로 시뮬레이션한다.
SQL = "capability:sql"
ADMIN = "capability:admin"
GENERAL = {("allow_select", SQL), ("justify_bulk_select", SQL)}
ENGINEERING = GENERAL | {("justify_update_delete", SQL)}
C_LEVEL = GENERAL | {("justify_update_delete", SQL), ("justify_grant", ADMIN)}  # 권한 관리자


def _checker(granted: set):
    async def check(user, relation, object_):
        return (relation, object_) in granted
    return check


@pytest.mark.asyncio
async def test_select_allow_all_tiers():
    for grants in (GENERAL, ENGINEERING, C_LEVEL):
        decision, _ = await gate_decision(_checker(grants), "u", RISK_SELECT)
        assert decision == DECISION_ALLOW


@pytest.mark.asyncio
async def test_bulk_select_justify_all_tiers():
    for grants in (GENERAL, ENGINEERING, C_LEVEL):
        decision, _ = await gate_decision(_checker(grants), "u", RISK_BULK_SELECT)
        assert decision == DECISION_JUSTIFY_AND_APPROVE


@pytest.mark.asyncio
async def test_update_delete_matrix():
    assert (await gate_decision(_checker(GENERAL), "u", RISK_UPDATE_DELETE))[0] == DECISION_DENY
    assert (await gate_decision(_checker(ENGINEERING), "u", RISK_UPDATE_DELETE))[0] == DECISION_JUSTIFY_AND_APPROVE
    assert (await gate_decision(_checker(C_LEVEL), "u", RISK_UPDATE_DELETE))[0] == DECISION_JUSTIFY_AND_APPROVE


@pytest.mark.asyncio
async def test_ddl_denied_all_tiers():
    for grants in (GENERAL, ENGINEERING, C_LEVEL):
        assert (await gate_decision(_checker(grants), "u", RISK_DDL))[0] == DECISION_DENY


@pytest.mark.asyncio
async def test_risk_deny_always_denied():
    assert (await gate_decision(_checker(C_LEVEL), "u", RISK_DENY))[0] == DECISION_DENY


@pytest.mark.asyncio
async def test_grant_justify_for_admin_only():
    # 권한 관리(RISK_GRANT)는 capability:admin justify_grant 보유자(c_level)만 JUSTIFY, 나머지 DENY
    assert (await gate_decision(_checker(C_LEVEL), "u", RISK_GRANT))[0] == DECISION_JUSTIFY_AND_APPROVE
    assert (await gate_decision(_checker(GENERAL), "u", RISK_GRANT))[0] == DECISION_DENY
    assert (await gate_decision(_checker(ENGINEERING), "u", RISK_GRANT))[0] == DECISION_DENY


@pytest.mark.asyncio
async def test_returns_nonempty_reason():
    decision, reason = await gate_decision(_checker(GENERAL), "u", RISK_UPDATE_DELETE)
    assert decision == DECISION_DENY
    assert isinstance(reason, str) and reason
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'RISK_GRANT' from 'core.sql.gate'`

- [ ] **Step 3: gate.py 일반화 구현**

`core/sql/gate.py`의 line 24~54(`CAPABILITY_OBJECT` 상수부터 함수 끝까지)를 다음으로 교체:
```python
# 권한 쓰기 위험도 — SQL AST risk(core.sql.risk)가 아니라 게이트 도메인 상수.
RISK_GRANT = "grant"

# 위험도 → (capability 객체, relation 베이스). 미매핑(RISK_DENY·미지원)은 DENY.
_RISK_GATE = {
    RISK_SELECT:        ("capability:sql",   "select"),
    RISK_BULK_SELECT:   ("capability:sql",   "bulk_select"),
    RISK_UPDATE_DELETE: ("capability:sql",   "update_delete"),
    RISK_DDL:           ("capability:sql",   "ddl"),
    RISK_GRANT:         ("capability:admin", "grant"),
}


async def gate_decision(
    check: Callable[[str, str, str], Awaitable[bool]],
    user_id: str,
    risk: str,
) -> tuple[str, str]:
    """(check, user_id, 위험도) → (결정, 사유).

    allow_<base>@<obj> 보유 → ALLOW, 없으면 justify_<base>@<obj> 보유 →
    JUSTIFY_AND_APPROVE, 둘 다 없으면 DENY. 미지원 위험도는 보수적으로 DENY.
    """
    entry = _RISK_GATE.get(risk)
    if entry is None:
        return DECISION_DENY, f"위험도={risk} 미지원 → DENY"
    obj, base = entry
    user = f"user:{user_id}"
    if await check(user, f"allow_{base}", obj):
        return DECISION_ALLOW, f"capability allow_{base}@{obj} 보유 → ALLOW"
    if await check(user, f"justify_{base}", obj):
        return DECISION_JUSTIFY_AND_APPROVE, f"capability justify_{base}@{obj} 보유 → JUSTIFY_AND_APPROVE"
    return DECISION_DENY, f"capability {base}@{obj} 미부여 → DENY"
```
(line 1~23의 docstring·import·DECISION 상수는 유지. `CAPABILITY_OBJECT`와 `RISK_TO_RELATION`은 위 교체로 제거된다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py -v`
Expected: 7개 PASS.

- [ ] **Step 5: CAPABILITY_OBJECT 잔재 확인**

Run: `grep -rn "CAPABILITY_OBJECT\|RISK_TO_RELATION" app/ core/ tests/`
Expected: 출력 없음(제거 완료). 남으면 해당 참조 정리.

- [ ] **Step 6: 커밋**

```bash
git add core/sql/gate.py tests/core/sql/test_gate.py
git commit -m "refactor(gate): _RISK_GATE 일반화 + RISK_GRANT(capability:admin) (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: model.fga — capability에 grant relation

**Files:**
- Modify: `fga/model.fga`
- Regenerate: `fga/model.json`

- [ ] **Step 1: grant relation 추가**

`fga/model.fga`의 `capability` 타입 끝(`define justify_ddl:` 줄 다음)에 추가:
```
    # 권한 관리(ADR-0029): capability:admin 인스턴스가 사용
    define allow_grant:           [user, department#member, role#member]
    define justify_grant:         [user, department#member, role#member]
```

- [ ] **Step 2: model.json 재생성**

`fga` CLI가 없으므로(SP2a에서 확인), `fga/model.json`의 `capability` type_definition에 두 relation을 수동 추가한다. 기존 `justify_ddl` relation의 JSON 구조를 복제해 `allow_grant`/`justify_grant`를 만든다:
- `relations`에 `"allow_grant": {"this": {}}`, `"justify_grant": {"this": {}}` 추가.
- `metadata.relations`에 각각 `directly_related_user_types: [{"type":"user"}, {"type":"department","relation":"member"}, {"type":"role","relation":"member"}]` 추가 (update_delete/ddl 계열과 동일 — user는 non-wildcard).

검증: `.venv/bin/python -c "import json; m=json.load(open('fga/model.json')); print('valid')"`

- [ ] **Step 3: 모델 재초기화 + 검증**

Run:
```bash
bash scripts/fga_init.sh
```
Expected: 새 authorization model id 발급, 오류 없음.

검증 — OpenFGA 최신 모델에 grant relation 존재 확인:
```bash
.venv/bin/python -c "
import asyncio
from openfga_sdk import OpenFgaClient, ClientConfiguration
from core.config import load_config
async def main():
    cfg = load_config()
    async with OpenFgaClient(ClientConfiguration(api_url=cfg.fga_api_url, store_id=cfg.fga_store_id)) as c:
        resp = await c.read_authorization_models()
        types = resp.authorization_models[0].type_definitions
        cap = next(t for t in types if t.type == 'capability')
        print('grant relations:', [r for r in cap.relations if 'grant' in r])
asyncio.run(main())
"
```
Expected: `grant relations: ['allow_grant', 'justify_grant']`

- [ ] **Step 4: 커밋**

```bash
git add fga/model.fga fga/model.json
git commit -m "feat(fga): capability에 allow_grant/justify_grant relation (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: FGAClient — grant_tuple / revoke_tuple

**Files:**
- Modify: `core/fga/client.py`
- Test: `tests/core/fga/test_client.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/core/fga/test_client.py` 끝에 추가:
```python
@pytest.mark.asyncio
async def test_grant_tuple_writes_and_invalidates():
    client = _client()
    with patch.object(client, "_write_fga_tuples", new=AsyncMock()) as mock_write, \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.grant_tuple("user:alice", "member", "department:engineering")
    mock_write.assert_awaited_once_with([
        {"user": "user:alice", "relation": "member", "object": "department:engineering"}
    ])
    mock_inv.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_tuple_deletes_and_invalidates():
    client = _client()

    class _FakeClient:
        def __init__(self):
            self.deleted = None
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def write(self, req):
            self.deleted = req

    fake = _FakeClient()
    with patch("openfga_sdk.OpenFgaClient", return_value=fake), \
         patch.object(client._cache, "invalidate", new=AsyncMock()) as mock_inv:
        await client.revoke_tuple("user:alice", "member", "department:engineering")
    assert fake.deleted is not None          # deletes 요청이 전달됨
    mock_inv.assert_awaited_once()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_client.py::test_grant_tuple_writes_and_invalidates -v`
Expected: FAIL — `AttributeError: 'FGAClient' object has no attribute 'grant_tuple'`

- [ ] **Step 3: 구현**

`core/fga/client.py`의 `add_department_member` 메서드 **직전**에 추가:
```python
    async def grant_tuple(self, subject: str, relation: str, object_: str) -> None:
        """범용 권한 부여(ADR-0029). 검증은 호출자(도구 plan)의 책임 — 여기선 쓰기만."""
        await self._write_fga_tuples([
            {"user": subject, "relation": relation, "object": object_}
        ])
        await self._cache.invalidate(subject)

    async def revoke_tuple(self, subject: str, relation: str, object_: str) -> None:
        """범용 권한 회수(ADR-0029). 멱등(없는 튜플 삭제는 무시)."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
        if self._config.api_key:
            from openfga_sdk.credentials import Credentials, CredentialConfiguration
            cfg.credentials = Credentials(
                method="api_token",
                configuration=CredentialConfiguration(api_token=self._config.api_key),
            )
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(user=subject, relation=relation, object=object_)]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._cache.invalidate(subject)
```
(`_cache.invalidate(subject)`는 subject가 `user:...`든 `department:...#member`든 캐시 키로 호출 — user 캐시만 실재하므로 dept subject는 사실상 no-op이며, folder_viewer/capability의 광역 무효화는 TTL에 맡긴다. ADR-0029 캐시 정책.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_client.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add core/fga/client.py tests/core/fga/test_client.py
git commit -m "feat(fga): 범용 grant_tuple/revoke_tuple (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: PermissionValidator — 화이트리스트 검증

**Files:**
- Create: `core/fga/permission_validator.py`
- Test: `tests/core/fga/test_permission_validator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/core/fga/test_permission_validator.py` 생성:
```python
from core.fga.permission_validator import PermissionValidator

# 화이트리스트를 직접 주입(config 파일 비의존 단위 테스트)
def _validator():
    return PermissionValidator(
        user_ids={"user-alice", "user-bob"},
        departments={"engineering", "sales"},
        folders={"/company", "/company/finance"},
    )


def test_valid_department_member_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-alice",
                      "relation": "member", "object": "department:engineering"})
    assert tup == ("user:user-alice", "member", "department:engineering", "grant")


def test_valid_folder_viewer_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:engineering#member",
                      "relation": "dept_viewer", "object": "folder:/company/finance"})
    assert tup == ("department:engineering#member", "dept_viewer", "folder:/company/finance", "grant")


def test_valid_capability_grant_to_department():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:engineering#member",
                      "relation": "justify_update_delete", "object": "capability:sql"})
    assert tup == ("department:engineering#member", "justify_update_delete", "capability:sql", "grant")


def test_valid_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-bob",
                      "relation": "member", "object": "department:sales"})
    assert tup[3] == "revoke"


def test_reject_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "member", "object": "department:engineering"}) is None


def test_reject_unknown_department():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "member", "object": "department:marketing"}) is None


def test_reject_unknown_folder():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "department:engineering#member",
                       "relation": "dept_viewer", "object": "folder:/secret"}) is None


def test_reject_unknown_capability_relation():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "allow_drop_everything", "object": "capability:sql"}) is None


def test_reject_type_mismatch_member_to_folder():
    # member relation인데 object가 folder → 타입 정합 위반
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "member", "object": "folder:/company"}) is None


def test_reject_bad_action():
    v = _validator()
    assert v.validate({"action": "delete_all", "subject": "user:user-alice",
                       "relation": "member", "object": "department:engineering"}) is None


def test_reject_whitespace_injection():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice x",
                       "relation": "member", "object": "department:engineering"}) is None


def test_catalog_text_contains_known_ids():
    v = _validator()
    text = v.catalog_text()
    assert "user-alice" in text and "engineering" in text and "/company/finance" in text
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.fga.permission_validator'`

- [ ] **Step 3: 구현**

`core/fga/permission_validator.py` 생성:
```python
"""권한 동작 화이트리스트 검증 (ADR-0029) — LangGraph 불가지.

LLM이 NL을 파싱한 {action, subject, relation, object}를 받아, id 유효성과
타입 정합을 화이트리스트로 검증한다. 통과 시 (subject, relation, object, action)
4-tuple, 실패 시 None. "이미 그 상태인가"는 멱등이라 검증하지 않는다(ADR-0029).
"""
from pathlib import Path

import yaml

# SP2a capability relation 고정 8종(ADR-0028) — grant 대상이 되는 SQL 권한.
_CAPABILITY_RELATIONS = {
    "allow_select", "justify_select",
    "allow_bulk_select", "justify_bulk_select",
    "allow_update_delete", "justify_update_delete",
    "allow_ddl", "justify_ddl",
}


class PermissionValidator:
    def __init__(self, *, user_ids: set, departments: set, folders: set) -> None:
        self._user_ids = user_ids
        self._departments = departments
        self._folders = folders

    @classmethod
    def from_config(
        cls,
        users_path: str = "config/users.yaml",
        folders_path: str = "config/folders.yaml",
    ) -> "PermissionValidator":
        users = yaml.safe_load(Path(users_path).read_text())["users"]
        user_ids = {u["user_id"] for u in users}
        departments: set = set()
        for u in users:
            departments |= set(u.get("departments", []))
        folders_raw = yaml.safe_load(Path(folders_path).read_text())["folders"]
        for spec in folders_raw.values():
            spec = spec or {}
            departments |= set(spec.get("dept_viewers", []))
        folders = set(folders_raw.keys())
        return cls(user_ids=user_ids, departments=departments, folders=folders)

    def _strip(self, value: str, prefix: str) -> str | None:
        return value[len(prefix):] if value.startswith(prefix) else None

    def validate(self, parsed: dict) -> tuple | None:
        action = parsed.get("action")
        subject = parsed.get("subject", "")
        relation = parsed.get("relation", "")
        object_ = parsed.get("object", "")
        if action not in ("grant", "revoke"):
            return None
        # 공백 주입 방어 — 모든 토큰은 공백 없는 id.
        if any(" " in x for x in (subject, relation, object_)):
            return None

        if relation == "member":
            uid = self._strip(subject, "user:")
            dept = self._strip(object_, "department:")
            if uid not in self._user_ids or dept not in self._departments:
                return None
        elif relation == "dept_viewer":
            dept = self._strip(subject, "department:")
            if dept is not None and dept.endswith("#member"):
                dept = dept[: -len("#member")]
            else:
                return None
            path = self._strip(object_, "folder:")
            if dept not in self._departments or path not in self._folders:
                return None
        elif relation in _CAPABILITY_RELATIONS:
            if object_ != "capability:sql":
                return None
            uid = self._strip(subject, "user:")
            if uid in self._user_ids:
                pass
            else:
                dept = self._strip(subject, "department:")
                if dept is not None and dept.endswith("#member"):
                    dept = dept[: -len("#member")]
                else:
                    return None
                if dept not in self._departments:
                    return None
        else:
            return None

        return (subject, relation, object_, action)

    def catalog_text(self) -> str:
        """LLM 파싱 프롬프트에 주입할 알려진 id 목록(정확한 id 유도용)."""
        users = ", ".join(sorted(self._user_ids))
        depts = ", ".join(sorted(self._departments))
        folders = ", ".join(sorted(self._folders))
        return f"유저: {users}\n부서: {depts}\n폴더: {folders}"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/core/fga/test_permission_validator.py -v`
Expected: 12개 PASS.

- [ ] **Step 5: 커밋**

```bash
git add core/fga/permission_validator.py tests/core/fga/test_permission_validator.py
git commit -m "feat(fga): PermissionValidator 화이트리스트 검증 (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: PERMISSION_PARSE_PROMPT + PermissionToolHandler

**Files:**
- Modify: `app/graph/prompts.py` (파일 끝에 추가)
- Create: `app/graph/tools/permission_tool.py`
- Test: `tests/app/graph/tools/test_permission_tool.py`

- [ ] **Step 1: 프롬프트 추가**

`app/graph/prompts.py` 파일 **끝**에 추가:
```python
# 권한 관리 NL → 구조화 파싱 (ADR-0029). {known_ids}/{instruction}는 .replace로 주입
# (JSON 예시의 중괄호와 format() 충돌 방지 — ADR-0021과 동일 회피).
PERMISSION_PARSE_PROMPT = """\
다음 권한 관리 지시를 OpenFGA 튜플 JSON으로 변환하라.

알려진 식별자(반드시 이 정확한 id를 사용):
{known_ids}

규칙:
- action: "grant"(부여) 또는 "revoke"(회수)
- 부서 멤버십: subject="user:<유저id>", relation="member", object="department:<부서>"
- 폴더 부서 접근권: subject="department:<부서>#member", relation="dept_viewer", object="folder:<경로>"
- SQL 권한: subject="user:<유저id>" 또는 "department:<부서>#member",
  relation 은 allow_select/justify_select/allow_bulk_select/justify_bulk_select/allow_update_delete/justify_update_delete/allow_ddl/justify_ddl 중 하나, object="capability:sql"

키는 action, subject, relation, object 네 개. JSON 객체만 출력(설명·코드펜스 금지).

지시: {instruction}

JSON:"""
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/app/graph/tools/test_permission_tool.py` 생성:
```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.tools.permission_tool import PermissionToolHandler
from core.fga.permission_validator import PermissionValidator
from core.sql.gate import RISK_GRANT
from core.sql.risk import RISK_DENY


def _validator():
    return PermissionValidator(
        user_ids={"user-alice"}, departments={"engineering"}, folders={"/company"}
    )


def _llm(reply: str):
    llm = MagicMock()
    llm.complete.return_value = reply
    return llm


def test_plan_valid_grant_returns_risk_grant():
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"instruction": "alice를 engineering에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-alice member department:engineering"


def test_plan_invalid_target_returns_deny():
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-eve","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "eve를 추가"})
    assert risk == RISK_DENY


def test_plan_unparseable_llm_output_returns_deny():
    handler = PermissionToolHandler(
        llm=_llm("죄송하지만 도와드릴 수 없습니다"),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "이상한 지시"})
    assert risk == RISK_DENY


@pytest.mark.asyncio
async def test_execute_grant_calls_grant_tuple():
    fga = MagicMock()
    fga.grant_tuple = AsyncMock()
    handler = PermissionToolHandler(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await handler.execute("grant user:user-alice member department:engineering")
    fga.grant_tuple.assert_awaited_once_with("user:user-alice", "member", "department:engineering")
    assert "완료" in result


@pytest.mark.asyncio
async def test_execute_revoke_calls_revoke_tuple():
    fga = MagicMock()
    fga.revoke_tuple = AsyncMock()
    handler = PermissionToolHandler(llm=MagicMock(), fga_client=fga, validator=_validator())
    await handler.execute("revoke user:user-alice member department:engineering")
    fga.revoke_tuple.assert_awaited_once_with("user:user-alice", "member", "department:engineering")
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.graph.tools.permission_tool'`

- [ ] **Step 4: 구현**

`app/graph/tools/permission_tool.py` 생성:
```python
"""권한 관리 도구 핸들러 (ADR-0029). NL 지시 → 구조화 파싱 → 화이트리스트 검증 →
(게이트) → FGA 튜플 쓰기. SQL 도구(query_business_data)와 동형.

plan은 LLM이 파싱한 {action,subject,relation,object}를 검증한다. 검증 실패는
RISK_DENY로 닫고, 통과는 RISK_GRANT(capability:admin 게이트 대상)로 낸다.
execute는 검증을 거친 planned_action만 받으므로 재검증 없이 튜플을 쓴다.
"""
import json

from langchain_core.tools import Tool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from core.sql.gate import RISK_GRANT
from core.sql.risk import RISK_DENY
from app.graph.prompts import PERMISSION_PARSE_PROMPT
from app.graph.nodes.sql_generate import _strip_code_fence

_DESCRIPTION = (
    "사내 권한을 관리한다(부여/회수): 부서 멤버십, 폴더 부서 접근권, SQL 실행 권한. "
    "예: '앨리스를 엔지니어링 부서에 추가', '세일즈 부서의 재무 폴더 열람권 회수'. "
    "instruction 인자에 한국어 자연어 지시를 그대로 넣는다."
)


class PermissionToolHandler:
    name = "manage_permission"

    def __init__(self, *, llm: LLMClient, fga_client: FGAClient, validator: PermissionValidator) -> None:
        self._llm = llm
        self._fga = fga_client
        self._validator = validator
        self.tool = Tool(name=self.name, description=_DESCRIPTION, func=lambda instruction: "")

    def plan(self, args: dict) -> tuple[str, str]:
        instruction = args["instruction"]
        prompt = (
            PERMISSION_PARSE_PROMPT
            .replace("{known_ids}", self._validator.catalog_text())
            .replace("{instruction}", instruction)
        )
        raw = self._llm.complete(prompt)
        try:
            parsed = json.loads(_strip_code_fence(raw))
        except Exception:
            return "권한 동작 파싱 실패", RISK_DENY
        if not isinstance(parsed, dict):
            return "권한 동작 파싱 실패", RISK_DENY
        validated = self._validator.validate(parsed)
        if validated is None:
            return "검증 실패: 유효하지 않은 권한 동작", RISK_DENY
        subject, relation, object_, action = validated
        return f"{action} {subject} {relation} {object_}", RISK_GRANT

    async def execute(self, planned_action: str) -> str:
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

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_permission_tool.py -v`
Expected: 5개 PASS.

- [ ] **Step 6: 커밋**

```bash
git add app/graph/prompts.py app/graph/tools/permission_tool.py tests/app/graph/tools/test_permission_tool.py
git commit -m "feat(tools): manage_permission 도구(plan 파싱·검증 + execute 튜플쓰기) (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: registry 등록 + builder 배선

**Files:**
- Modify: `app/graph/tools/registry.py`
- Modify: `app/graph/builder.py:65`
- Test: `tests/app/graph/tools/test_registry.py` (없으면 생성)

- [ ] **Step 1: 실패 테스트 작성**

`tests/app/graph/tools/test_registry.py` 생성(있으면 케이스 추가):
```python
from unittest.mock import MagicMock

from app.graph.tools.registry import build_tool_registry


def test_registry_includes_both_tools():
    reg = build_tool_registry(llm=MagicMock(), sql_pool=MagicMock(), fga_client=MagicMock())
    assert "query_business_data" in reg.handlers
    assert "manage_permission" in reg.handlers
    names = {t.name for t in reg.tool_defs}
    assert names == {"query_business_data", "manage_permission"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v`
Expected: FAIL — `build_tool_registry() got an unexpected keyword argument 'fga_client'` 또는 manage_permission 부재.

- [ ] **Step 3: registry 구현**

`app/graph/tools/registry.py` 전체를 다음으로 교체:
```python
"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import Tool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from app.graph.tools.sql_tool import SqlToolHandler
from app.graph.tools.permission_tool import PermissionToolHandler


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolHandler
    tool_defs: list[Tool]   # bind_tools용


def build_tool_registry(*, llm: LLMClient, sql_pool, fga_client: FGAClient) -> ToolRegistry:
    sql = SqlToolHandler(llm=llm, sql_pool=sql_pool)
    permission = PermissionToolHandler(
        llm=llm, fga_client=fga_client, validator=PermissionValidator.from_config()
    )
    handlers = {sql.name: sql, permission.name: permission}
    tool_defs = [sql.tool, permission.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)
```

- [ ] **Step 4: builder 배선**

`app/graph/builder.py` line 65를:
```python
    registry = build_tool_registry(llm=llm, sql_pool=sql_pool, fga_client=fga_client)
```
로 수정(`fga_client=fga_client` 추가). builder의 `fga_client`는 같은 함수 인자로 이미 존재(검증: line 49~60 시그니처).

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/tools/test_registry.py -v && .venv/bin/python -c "import app.graph.builder"`
Expected: PASS + import 정상.

- [ ] **Step 6: 커밋**

```bash
git add app/graph/tools/registry.py app/graph/builder.py tests/app/graph/tools/test_registry.py
git commit -m "feat(tools): manage_permission 레지스트리 등록 + builder fga_client 배선 (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: 시드 — capability:admin justify_grant

**Files:**
- Modify: `scripts/seed_fga.py`

- [ ] **Step 1: _CAPABILITY_GRANTS에 grant 부여 추가**

`scripts/seed_fga.py`의 `_CAPABILITY_GRANTS` 리스트 끝(`role:c_level#member ... justify_update_delete` 항목 다음)에 추가:
```python
    {"user": "role:c_level#member", "relation": "justify_grant", "object": "capability:admin"},
```
주석도 한 줄 갱신(있으면): `# DDL 전원 DENY(튜플 없음) / 권한관리는 c_level만 justify_grant(ADR-0029).`

- [ ] **Step 2: 재시드**

Run:
```bash
.venv/bin/python -m scripts.seed_fga 2>&1 | tail -6
```
Expected: 출력에 `role:c_level#member justify_grant capability:admin` 포함, 튜플 수 +1.

- [ ] **Step 3: 통합 검증 — c_level만 grant 게이트 통과**

config/users.yaml에서 c_level 유저(예: `user-admin`)와 일반 유저(예: sales 소속) id를 확인 후:
```bash
.venv/bin/python -c "
import asyncio, asyncpg
from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.sql.gate import gate_decision, RISK_GRANT

async def main():
    cfg = load_config()
    fc = FGAConfig(api_url=cfg.fga_api_url, store_id=cfg.fga_store_id, api_key=cfg.fga_api_key, cache_ttl_seconds=cfg.fga_cache_ttl_seconds)
    pool = await asyncpg.create_pool(cfg.postgres_dsn)
    client = FGAClient(config=fc, cache=make_cache_backend(cfg.fga_cache_backend, pool), pg_pool=pool)
    for uid, label in [('user-admin','c_level'), ('<general_uid>','general')]:
        d, _ = await gate_decision(client.check, uid, RISK_GRANT)
        print(label, 'grant', d)
    await pool.close()
asyncio.run(main())
"
```
Expected: `c_level grant JUSTIFY_AND_APPROVE` / `general grant DENY`. (`<general_uid>`는 실제 sales 등 일반 유저로 치환.)

- [ ] **Step 4: 커밋**

```bash
git add scripts/seed_fga.py
git commit -m "feat(seed): capability:admin justify_grant를 c_level에 부여 (ADR-0029)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: 통합 테스트 + 회귀 + ADR 종단

**Files:**
- Modify: `tests/app/graph/test_builder.py`
- Modify: `docs/superpowers/decisions/ADR-0029-permission-management-tool.md` (Status)

- [ ] **Step 1: 통합 테스트 추가 (test_builder.py)**

`tests/app/graph/test_builder.py`에 추가. `_mock_fga_client`에 `grant_tuple`/`revoke_tuple` AsyncMock과 capability 부여를 반영한다(헬퍼는 SP2a에서 capabilities 파라미터 보유 — `(relation, object)` 판정으로 맞춰야 하면 그에 맞게 부여). 새 테스트:
```python
def _perm_tool_call_msg(instruction="alice를 eng 부서에 추가", tc_id="p1"):
    return AIMessage(
        content="",
        tool_calls=[{"name": "manage_permission", "args": {"instruction": instruction}, "id": tc_id}],
    )


@pytest.mark.asyncio
async def test_manage_permission_justify_then_resume_executes():
    """권한 관리(RISK_GRANT) → capability:admin justify_grant 보유자 → JUSTIFY interrupt →
    사유 resume → grant_tuple 실행 → 최종 답변."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "alice 추가",                                                          # rewrite
        "tool_call",                                                          # router
        '{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}',  # permission plan 파싱
    ]
    chat = _mock_chat_model([
        _perm_tool_call_msg(),                                               # 1차: 도구 호출 → interrupt
        AIMessage(content="앨리스를 엔지니어링에 추가했습니다."),               # 2차: resume 후 최종 답변
    ])
    fga = _mock_fga_client(roles=["c_level"], capabilities=[("justify_grant", "capability:admin")])
    fga.grant_tuple = AsyncMock()
    graph = build_graph(
        retriever=_make_retriever(), llm=llm, fga_client=fga,
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), chat_model=chat,
    )
    config = {"configurable": {"thread_id": "perm-justify-1"}}

    result = await graph.ainvoke(_make_initial_state("alice를 eng에 추가해"), config=config)
    assert "__interrupt__" in result

    final = await graph.ainvoke(Command(resume="신규 입사자 부서 배정"), config=config)
    assert final["answer"] == "앨리스를 엔지니어링에 추가했습니다."
    fga.grant_tuple.assert_awaited_once_with("user:user-alice", "member", "department:engineering")


@pytest.mark.asyncio
async def test_manage_permission_deny_for_non_admin():
    """grant 권한(justify_grant) 없는 사용자 → DENY, interrupt 없이 거부 답변."""
    llm = MagicMock()
    llm.complete.side_effect = [
        "alice 추가",                                                          # rewrite
        "tool_call",                                                          # router
        '{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}',  # plan 파싱
    ]
    chat = _mock_chat_model([
        _perm_tool_call_msg(),
        AIMessage(content="권한이 없어 실행할 수 없습니다."),
    ])
    fga = _mock_fga_client(departments=["sales"])   # justify_grant 미보유
    fga.grant_tuple = AsyncMock()
    graph = build_graph(
        retriever=_make_retriever(), llm=llm, fga_client=fga,
        audit_sink=AsyncMock(), sql_pool=_mock_sql_pool(), chat_model=chat,
    )
    config = {"configurable": {"thread_id": "perm-deny-1"}}

    final = await graph.ainvoke(_make_initial_state("alice를 eng에 추가해"), config=config)
    assert "__interrupt__" not in final
    assert final["answer"] == "권한이 없어 실행할 수 없습니다."
    fga.grant_tuple.assert_not_called()
```

> **선행 확인**: SP2a에서 `_mock_fga_client`의 `check`가 `capabilities` set으로 `relation in caps` 판정한다. SP2b 게이트는 `(relation, object)` 둘 다 보므로, `_mock_fga_client`의 `check`를 `(relation, object_) in caps` 판정으로 바꾸고 기존 tool_call 테스트의 capability 인자도 `("allow_select","capability:sql")` 형태로 갱신해야 한다. 이 갱신을 Step 1에 포함하라(기존 SP2a tool_call 테스트가 깨지지 않도록 함께 수정).

- [ ] **Step 2: 통합 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/app/graph/test_builder.py -v`
Expected: 신규 2개 포함 전부 PASS.

- [ ] **Step 3: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -3`
Expected: `0 failed`.

- [ ] **Step 4: ADR Status 갱신 + 인덱스**

`ADR-0029` Status를 `⚪ 제안됨` → `🟢 적용완료`로 변경 후:
```bash
.venv/bin/python -m scripts.gen_adr_index
```

- [ ] **Step 5: 커밋**

```bash
git add tests/app/graph/test_builder.py docs/superpowers/decisions/
git commit -m "test(builder): manage_permission tool_call 경로 통합 테스트 + ADR-0029 적용완료 (SP2b)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review 결과

- **Spec coverage:** ADR-0029 ①~⑦ 전부 매핑 — ①도구=Task5, ②게이트=Task1, ③모델=Task2, ④FGAClient=Task3, ⑤검증기=Task4, ⑥시드=Task7, ⑦HITL무변경=Task8 통합테스트로 검증. registry/builder 배선=Task6.
- **Placeholder scan:** Task7 Step3 `<general_uid>`는 의도적 치환 지시. 그 외 placeholder 없음.
- **Type consistency:** `PermissionValidator(user_ids=, departments=, folders=)` 생성자가 Task4 정의·Task5 테스트 일치. `validate()`가 `(subject, relation, object, action)` 4-tuple 반환 — Task4·5 일치. `grant_tuple(subject, relation, object_)`·`revoke_tuple` 시그니처가 Task3 정의·Task5 execute 호출 일치. `RISK_GRANT`(gate.py)·`RISK_DENY`(risk.py) import 출처 일관. planned_action 포맷 `"{action} {subject} {relation} {object}"`이 Task5 plan 생성·execute split 일치.
- **알려진 리스크:** Task8이 SP2a `_mock_fga_client` check 시그니처를 `(relation, object)` 판정으로 바꾸므로 기존 tool_call 테스트 capability 인자도 함께 갱신해야 함(Step1 선행 확인에 명시).

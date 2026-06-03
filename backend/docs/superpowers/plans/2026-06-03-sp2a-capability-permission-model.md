# SP2a: SQL 게이트 OpenFGA capability 통일 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SQL 게이트 결정을 `core/sql/gate.py`의 하드코딩 매트릭스에서 OpenFGA `capability:sql`의 2층 relation(`allow_*`/`justify_*`) Check로 옮겨, SQL 권한을 디렉토리 권한처럼 "부여 가능한 데이터"로 만든다. 기존 동작은 회귀 0으로 보존한다.

**Architecture:** OpenFGA에 `capability` 타입을 신설하고 위험도 4종×2층 relation을 둔다. `gate_decision(check, user_id, risk)`가 `allow_*`→ALLOW, `justify_*`→JUSTIFY, 둘 다 없으면 DENY로 3-state를 판정한다. 시드(`seed_fga.py` 상수)가 현행 매트릭스를 튜플로 재현한다. `tool_gate_node`는 `identity_tier`/`gate_lookup` 대신 `gate_decision`을 호출하되 감사로그용 신원 조회는 유지한다.

**Tech Stack:** OpenFGA(openfga_sdk), Python 3.11, pytest. 상세 설계: `docs/superpowers/decisions/ADR-0028-capability-permission-model.md`

---

## File Structure

- `fga/model.fga` (수정) — `capability` 타입 추가. 권한 종류의 단일 출처.
- `fga/model.json` (재생성) — `model.fga`의 컴파일 산출물. 런타임 모델.
- `core/fga/client.py` (수정) — `check()` 단일 Check 메서드 추가.
- `core/sql/gate.py` (재작성) — 매트릭스 제거, `gate_decision`(async) + `CapabilityChecker` Protocol.
- `app/graph/nodes/tool_gate.py` (수정) — `gate_decision` 호출로 교체.
- `scripts/seed_fga.py` (수정) — `_CAPABILITY_GRANTS` 상수로 기본부여 튜플 추가.
- `tests/core/fga/test_client.py` (수정) — `check()` 테스트 추가.
- `tests/core/sql/test_gate.py` (재작성) — fake checker로 `gate_decision` 검증.
- `tests/app/graph/nodes/test_tool_gate.py` (수정) — `_fga` 헬퍼에 `check` 추가, 3개 테스트 갱신.

---

## Task 0: 브랜치 생성

- [ ] **Step 1: feat 브랜치 생성**

Run:
```bash
cd /Users/acacian/vscode/company-rag/backend && git checkout -b feat/sp2a-capability-model
```
Expected: `Switched to a new branch 'feat/sp2a-capability-model'`

> 참고: 작업 디렉토리는 항상 `backend/`. 인터프리터는 `.venv/bin/python`. 테스트는 `.venv/bin/python -m pytest`.

---

## Task 1: FGAClient.check() — 단일 Check 메서드

**Files:**
- Modify: `core/fga/client.py` (`_list_fga_objects` 다음, line 63 위쪽에 추가)
- Test: `tests/core/fga/test_client.py`

- [ ] **Step 1: Write the failing test**

`tests/core/fga/test_client.py` 끝에 추가:
```python
@pytest.mark.asyncio
async def test_check_returns_allowed_true():
    client = _client()

    class _Resp:
        allowed = True

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def check(self, req): return _Resp()

    with patch("core.fga.client.OpenFgaClient", return_value=_FakeClient()):
        result = await client.check("user:alice", "allow_select", "capability:sql")
    assert result is True


@pytest.mark.asyncio
async def test_check_returns_allowed_false():
    client = _client()

    class _Resp:
        allowed = False

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def check(self, req): return _Resp()

    with patch("core.fga.client.OpenFgaClient", return_value=_FakeClient()):
        result = await client.check("user:bob", "allow_ddl", "capability:sql")
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/fga/test_client.py::test_check_returns_allowed_true -v`
Expected: FAIL — `AttributeError: 'FGAClient' object has no attribute 'check'`

- [ ] **Step 3: Write minimal implementation**

`core/fga/client.py`의 `_list_fga_objects` 메서드 정의 **직전**(line 63 `async def _list_fga_objects` 위)에 추가:
```python
    async def check(self, user: str, relation: str, object_: str) -> bool:
        """단일 (user, relation, object) 권한 Check. capability/folder 등 모든 타입 공용."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientCheckRequest
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        async with OpenFgaClient(cfg) as client:
            resp = await client.check(
                ClientCheckRequest(user=user, relation=relation, object=object_)
            )
            return bool(resp.allowed)
```

> 패치 대상이 `core.fga.client.OpenFgaClient`이려면 `OpenFgaClient`가 모듈 네임스페이스에 보여야 한다. 위 구현은 메서드 내부 import라 테스트의 `patch("core.fga.client.OpenFgaClient", ...)`가 import된 심볼을 가로채지 못할 수 있다. **따라서 이 테스트가 통과하도록 import를 함수 밖(모듈 상단)으로 올리지 말고**, 테스트를 다음과 같이 메서드 내부 import 지점을 패치하도록 맞춘다 — Step 1의 `patch("core.fga.client.OpenFgaClient")`는 메서드가 `from openfga_sdk import OpenFgaClient`로 매번 새로 바인딩하므로 `patch("openfga_sdk.OpenFgaClient", ...)`로 바꿔야 한다. Step 1 테스트의 두 `patch(...)` 인자를 `"openfga_sdk.OpenFgaClient"`로 수정한 뒤 진행한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/fga/test_client.py -v`
Expected: PASS (기존 테스트 포함 전부 통과)

- [ ] **Step 5: Commit**

```bash
git add core/fga/client.py tests/core/fga/test_client.py
git commit -m "feat(fga): FGAClient.check 단일 권한 Check 추가 (ADR-0028)"
```

---

## Task 2: gate.py 재작성 — capability 기반 gate_decision

**Files:**
- Rewrite: `core/sql/gate.py`
- Rewrite: `tests/core/sql/test_gate.py`

- [ ] **Step 1: Write the failing test (test_gate.py 전체 교체)**

`tests/core/sql/test_gate.py` 전체를 다음으로 교체:
```python
import pytest

from core.sql.gate import (
    gate_decision,
    CAPABILITY_OBJECT,
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

# 시드 기본부여를 user 단위로 푼 상태(ADR-0028). OpenFGA Check가 상속을 풀어
# 반환하는 결과를 set으로 시뮬레이션한다.
GENERAL = {"allow_select", "justify_bulk_select"}              # 일반 부서원
ENGINEERING = GENERAL | {"justify_update_delete"}             # engineering 부서
C_LEVEL = GENERAL | {"justify_update_delete"}                 # c_level 역할


def _checker(granted: set):
    async def check(user, relation, object_):
        assert object_ == CAPABILITY_OBJECT
        return relation in granted
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
async def test_returns_nonempty_reason():
    decision, reason = await gate_decision(_checker(GENERAL), "u", RISK_UPDATE_DELETE)
    assert decision == DECISION_DENY
    assert isinstance(reason, str) and reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'gate_decision' from 'core.sql.gate'`

- [ ] **Step 3: Write implementation (gate.py 전체 교체)**

`core/sql/gate.py` 전체를 다음으로 교체:
```python
"""capability 게이트 (ADR-0028, 3-state 의미 ADR-0027 유지).

SQL 위험도(core.sql.risk)를 OpenFGA capability:sql 의 2층 relation
(allow_*/justify_*) Check로 교차해 3-state 결정을 내린다. 게이트 정책은
코드 매트릭스가 아니라 OpenFGA 튜플에 있다 — 신원 조회·감사 기록은 노드의 책임이다.

DBA 부재 전제(ADR-0027): 회색지대는 외부 결재 대기가 아니라, 질문자 본인이
사유를 남기고 자기책임으로 통과(JUSTIFY_AND_APPROVE)하는 self-service 흐름이다.
"""
from typing import Awaitable, Callable, Protocol

from core.sql.risk import (
    RISK_SELECT,
    RISK_BULK_SELECT,
    RISK_UPDATE_DELETE,
    RISK_DDL,
)

# 게이트 3-state (ADR-0027)
DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_JUSTIFY_AND_APPROVE = "JUSTIFY_AND_APPROVE"

# capability 인스턴스 — SQL 권한의 단일 객체
CAPABILITY_OBJECT = "capability:sql"

# 위험도 → capability relation 접미. 미매핑(RISK_DENY·미지원)은 DENY.
RISK_TO_RELATION = {
    RISK_SELECT: "select",
    RISK_BULK_SELECT: "bulk_select",
    RISK_UPDATE_DELETE: "update_delete",
    RISK_DDL: "ddl",
}


class CapabilityChecker(Protocol):
    """gate_decision이 의존하는 최소 인터페이스. FGAClient가 구조적으로 만족한다."""
    async def check(self, user: str, relation: str, object_: str) -> bool: ...


async def gate_decision(
    check: Callable[[str, str, str], Awaitable[bool]],
    user_id: str,
    risk: str,
) -> tuple[str, str]:
    """(check, user_id, 위험도) → (결정, 사유).

    allow_<risk> 보유 → ALLOW, 없으면 justify_<risk> 보유 → JUSTIFY_AND_APPROVE,
    둘 다 없으면 DENY. 미지원 위험도(RISK_DENY 등)는 보수적으로 DENY.
    """
    suffix = RISK_TO_RELATION.get(risk)
    if suffix is None:
        return DECISION_DENY, f"위험도={risk} 미지원 → DENY"
    user = f"user:{user_id}"
    if await check(user, f"allow_{suffix}", CAPABILITY_OBJECT):
        return DECISION_ALLOW, f"capability allow_{suffix} 보유 → ALLOW"
    if await check(user, f"justify_{suffix}", CAPABILITY_OBJECT):
        return DECISION_JUSTIFY_AND_APPROVE, f"capability justify_{suffix} 보유 → JUSTIFY_AND_APPROVE"
    return DECISION_DENY, f"capability {suffix} 미부여 → DENY"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/sql/test_gate.py -v`
Expected: PASS (7개 테스트 통과)

- [ ] **Step 5: Commit**

```bash
git add core/sql/gate.py tests/core/sql/test_gate.py
git commit -m "refactor(gate): 매트릭스 제거, capability Check 기반 gate_decision (ADR-0028)"
```

---

## Task 3: tool_gate_node — gate_decision 호출로 교체 (+ 레거시 gate_node 제거)

> **plan 보정(실행 중 발견):** `app/graph/nodes/gate.py`의 `gate_node`(ADR-0016 신원×위험도 노드)가 `identity_tier`/`gate_lookup`을 import한다. 이 노드는 builder에 `add_node`로 등록되지 않은 **미연결 레거시**(ADR-0023의 `tool_gate_node`가 기능 대체)다. 사용자 결정: **gate_node와 그 테스트를 제거**한다.

**Files:**
- Modify: `app/graph/nodes/tool_gate.py:11-16, 28-44`
- Modify: `tests/app/graph/nodes/test_tool_gate.py:8-12, 41, 59, 76`
- Delete: `app/graph/nodes/gate.py` (미연결 레거시)
- Delete: `tests/app/graph/nodes/test_gate.py` (위 노드의 테스트)
- Modify: `tests/app/graph/test_builder.py` (**plan 보정, Task 6에서 발견**) — 통합 테스트의 `_mock_fga_client`에 `check` 미설정 시 게이트가 깨진다. 헬퍼에 `capabilities` 파라미터 + async `check` 추가하고, 각 tool_call 테스트에 위험도별 capability 부여(allow→`allow_select`, justify→`justify_bulk_select`, deny→없음).

- [ ] **Step 1: Update test helper and cases (test_tool_gate.py)**

`tests/app/graph/nodes/test_tool_gate.py`의 `_fga` 헬퍼(line 8-12)를 다음으로 교체:
```python
def _fga(roles, depts, capabilities=()):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=depts)
    caps = set(capabilities)

    async def check(user, relation, object_):
        return relation in caps

    fga.check = check
    return fga
```

그리고 3개 테스트의 `_fga(...)` 호출을 위험도에 맞는 capability로 수정:
- `test_allow_executes_and_appends_tool_message` (risk=select): line 41을
  `fga_client=_fga([], ["sales"], capabilities=["allow_select"]),` 로.
- `test_deny_appends_rejection_without_executing` (risk=update_delete, 부여 없음): line 59을
  `fga_client=_fga([], ["sales"]),` 로 (capabilities 비움 → DENY). **변경 불필요하면 그대로 두되 인자 형태만 확인.**
- `test_justify_records_pending_without_executing` (risk=bulk_select): line 76을
  `fga_client=_fga([], ["sales"], capabilities=["justify_bulk_select"]),` 로.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -v`
Expected: FAIL — `test_allow...`가 DENY로 떨어져 실패(아직 노드가 identity_tier/gate_lookup 사용).

- [ ] **Step 3: Update tool_gate_node**

`app/graph/nodes/tool_gate.py` line 13-16의 import를:
```python
from core.sql.gate import (
    gate_decision,
    DECISION_ALLOW, DECISION_DENY, DECISION_JUSTIFY_AND_APPROVE,
)
```
로 교체 (identity_tier, gate_lookup 제거).

line 28-32의 함수 시작부에서 `tier = identity_tier(...)` 줄을 삭제:
```python
async def tool_gate_node(state: dict, *, registry, fga_client: FGAClient, audit_sink: AuditSink) -> dict:
    user_id = state["user_id"]
    roles = await fga_client.user_roles(user_id)
    departments = await fga_client.user_departments(user_id)
```
(`tier = identity_tier(roles, departments)` 줄 제거 — 신원 조회 2줄은 감사로그용으로 유지.)

line 44의 `decision, reason = gate_lookup(tier, risk)`를:
```python
        decision, reason = await gate_decision(fga_client.check, user_id, risk)
```
로 교체.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/app/graph/nodes/test_tool_gate.py -v`
Expected: PASS (3개 통과)

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/tool_gate.py tests/app/graph/nodes/test_tool_gate.py
git commit -m "refactor(tool_gate): gate_decision(capability Check) 호출로 전환 (ADR-0028)"
```

---

## Task 4: fga/model.fga — capability 타입 추가

**Files:**
- Modify: `fga/model.fga` (파일 끝에 추가)
- Regenerate: `fga/model.json`

- [ ] **Step 1: Add capability type**

`fga/model.fga` 파일 끝(line 33 `define can_read:` 아래)에 추가:
```
type capability
  relations
    # SQL 권한 2층(ADR-0028): allow_* → ALLOW, justify_* → JUSTIFY_AND_APPROVE
    define allow_select:          [user:*, department#member, role#member]
    define justify_select:        [user:*, department#member, role#member]
    define allow_bulk_select:     [user:*, department#member, role#member]
    define justify_bulk_select:   [user:*, department#member, role#member]
    define allow_update_delete:   [user, department#member, role#member]
    define justify_update_delete: [user, department#member, role#member]
    define allow_ddl:             [user, department#member, role#member]
    define justify_ddl:           [user, department#member, role#member]
```

- [ ] **Step 2: Regenerate model.json**

`fga/model.json`은 `model.fga`의 JSON 컴파일 산출물이다. 다음 중 동작하는 방법으로 재생성:
```bash
# 방법 A: fga CLI가 있으면
fga model transform --file fga/model.fga > fga/model.json
```
fga CLI가 없으면 `scripts/fga_init.sh`가 어떤 파일(`.fga` vs `.json`)을 OpenFGA에 올리는지 확인하라:
```bash
grep -n "model" scripts/fga_init.sh
```
- `fga_init.sh`가 `.fga`를 직접 쓰면 `model.json` 재생성 불필요(Step 3에서 init만).
- `.json`을 쓰면 fga CLI 설치(`brew install openfga/tap/fga`) 후 방법 A 실행.

- [ ] **Step 3: Re-init FGA store & verify model loads**

Run (OpenFGA 컨테이너가 떠 있어야 함 — `docker-compose up -d` 필요 시):
```bash
bash scripts/fga_init.sh
```
Expected: 모델 업로드 성공 메시지(오류 없음).

- [ ] **Step 4: Commit**

```bash
git add fga/model.fga fga/model.json
git commit -m "feat(fga): capability 타입(SQL 권한 2층 relation) 추가 (ADR-0028)"
```

---

## Task 5: seed_fga.py — capability 기본부여

**Files:**
- Modify: `scripts/seed_fga.py:31-85`

- [ ] **Step 1: Add _CAPABILITY_GRANTS constant**

`scripts/seed_fga.py`의 `_build_tuples` 함수 **정의 직전**(line 31 `def _build_tuples` 위)에 추가:
```python
# capability:sql 기본부여(ADR-0028) — 현행 게이트 매트릭스를 튜플로 재현.
# SELECT 전원 ALLOW / BULK_SELECT 전원 JUSTIFY / UPDATE_DELETE engineering·c_level JUSTIFY / DDL 전원 DENY(튜플 없음).
_CAPABILITY_GRANTS = [
    {"user": "user:*", "relation": "allow_select", "object": "capability:sql"},
    {"user": "user:*", "relation": "justify_bulk_select", "object": "capability:sql"},
    {"user": "department:engineering#member", "relation": "justify_update_delete", "object": "capability:sql"},
    {"user": "role:c_level#member", "relation": "justify_update_delete", "object": "capability:sql"},
]
```

- [ ] **Step 2: Append grants in _build_tuples**

`_build_tuples`의 `return tuples` (line 85) **직전**에 추가:
```python
    # 3) capability 기본부여(ADR-0028)
    tuples.extend(_CAPABILITY_GRANTS)

```

- [ ] **Step 3: Re-seed & smoke-check**

Run (OpenFGA·Postgres 기동 상태에서):
```bash
.venv/bin/python -m scripts.seed_fga 2>&1 | tail -6
```
Expected: 출력 마지막에 `capability:sql` 튜플 4건이 보이고 `FGA 시드 완료 (N 튜플)` (N은 기존+4).

- [ ] **Step 4: Verify decisions match legacy matrix (integration)**

OpenFGA가 기동된 상태에서 실제 Check로 매트릭스 재현을 확인:
```bash
.venv/bin/python -c "
import asyncio
from core.config import load_config
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.sql.gate import gate_decision
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL
import asyncpg

async def main():
    cfg = load_config()
    fc = FGAConfig(api_url=cfg.fga_api_url, store_id=cfg.fga_store_id, api_key=cfg.fga_api_key, cache_ttl_seconds=cfg.fga_cache_ttl_seconds)
    pool = await asyncpg.create_pool(cfg.postgres_dsn)
    client = FGAClient(config=fc, cache=make_cache_backend(cfg.fga_cache_backend, pool), pg_pool=pool)
    # 실제 시드된 user_id로 교체: 일반=sales 소속, eng=engineering 소속, c=c_level 역할
    for uid, label in [('<general_uid>','general'), ('<eng_uid>','engineering'), ('<c_uid>','c_level')]:
        for risk in (RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL):
            d, _ = await gate_decision(client.check, uid, risk)
            print(label, risk, d)
    await pool.close()
asyncio.run(main())
"
```
Expected (config/users.yaml의 실제 uid로 `<...>` 치환 후):
```
general select ALLOW / bulk_select JUSTIFY_AND_APPROVE / update_delete DENY / ddl DENY
engineering ... update_delete JUSTIFY_AND_APPROVE ...
c_level ... update_delete JUSTIFY_AND_APPROVE ...
```
기존 매트릭스(`ADR-0027`)와 동일하면 회귀 0 확인.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_fga.py
git commit -m "feat(seed): capability:sql 기본부여로 게이트 매트릭스 재현 (ADR-0028)"
```

---

## Task 6: 회귀 검증 · ADR 종단

**Files:**
- Modify: `docs/superpowers/decisions/ADR-0028-capability-permission-model.md` (Status)
- Possibly modify: `docs/superpowers/decisions/ADR-0016-identity-risk-sql-gate.md` (Status)

- [ ] **Step 1: Full unit suite**

Run: `.venv/bin/python -m pytest tests/core/sql tests/core/fga tests/app/graph/nodes -v`
Expected: 전부 PASS. 실패 시 systematic-debugging.

- [ ] **Step 2: grep 잔재 확인 (identity_tier/gate_lookup 미참조)**

Run: `grep -rn "identity_tier\|gate_lookup\|TIER_GENERAL\|TIER_ENGINEERING\|TIER_C_LEVEL" app/ core/ scripts/`
Expected: 출력 없음(전부 제거됨). 남아있으면 해당 참조 정리.

- [ ] **Step 3: eval 회귀 점수**

Run: `.venv/bin/python -m tests.eval.runner 2>&1 | tail -20`
Expected: 점수가 기준선 대비 유지/상승. 하락 시 원인 명시.

- [ ] **Step 4: ADR Status 갱신**

`ADR-0028` 제목 아래 Status를 `⚪ 제안됨` → `🟢 적용완료`로 변경.

`ADR-0016`은 매트릭스 메커니즘이 capability Check로 대체되었으나 위험도 분류·3-state 어휘는 유지된다 — Status를 `🟣 대체됨 → [ADR-0028](ADR-0028-capability-permission-model.md)`로 변경(부분 대체이므로 본문에 "매트릭스 메커니즘만 대체, 위험도·3-state는 유지" 한 줄 명시).

그 후 인덱스 재생성:
```bash
.venv/bin/python -m scripts.gen_adr_index
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/decisions/
git commit -m "docs(adr): ADR-0028 적용완료, ADR-0016 대체됨 종단 (SP2a)"
```

---

## Self-Review 결과

- **Spec coverage:** ADR-0028 ①~⑥ 전부 Task 매핑 — ①model.fga=Task4, ②check=Task1, ③gate.py=Task2, ④tool_gate=Task3, ⑤seed=Task5, ⑥회귀/DoD=Task6. 빠짐 없음.
- **Placeholder scan:** Task5 Step4의 `<general_uid>` 등은 의도적 치환 지시(실제 users.yaml 값). 그 외 placeholder 없음.
- **Type consistency:** `gate_decision(check, user_id, risk)` 시그니처가 Task2 정의·Task3 호출 일치. `CAPABILITY_OBJECT="capability:sql"`·relation 접미(`allow_select` 등)가 gate.py·model.fga·seed 전반 일치.
- **알려진 리스크:** Task1 Step3의 patch 대상(`openfga_sdk.OpenFgaClient` vs `core.fga.client.OpenFgaClient`)은 메서드 내부 import 특성상 전자가 맞다 — Step1 테스트 작성 시 반영.

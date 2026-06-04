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
async def test_justify_only_risks_never_check_allow():
    """SELECT 외 모든 위험군은 allow_* relation을 조회하지 않는다.

    allow_bulk_select/allow_ddl/allow_grant는 모델에서 제거됐으므로, 게이트가
    이들을 Check하면 실제 OpenFGA에서 undefined-relation 에러가 난다. justify-only
    경로만 타는지 정합성을 가드한다(원래 admin 조회 버그와 같은 부류 방지).
    """
    for risk in (RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL, RISK_GRANT):
        seen: list[str] = []

        async def check(user, relation, object_, _seen=seen):
            _seen.append(relation)
            return False

        await gate_decision(check, "u", risk)
        assert not any(r.startswith("allow_") for r in seen), f"{risk} → {seen}"


@pytest.mark.asyncio
async def test_returns_nonempty_reason():
    decision, reason = await gate_decision(_checker(GENERAL), "u", RISK_UPDATE_DELETE)
    assert decision == DECISION_DENY
    assert isinstance(reason, str) and reason

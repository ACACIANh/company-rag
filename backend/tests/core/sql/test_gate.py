from core.sql.gate import (
    identity_tier,
    gate_lookup,
    TIER_GENERAL,
    TIER_ENGINEERING,
    TIER_C_LEVEL,
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


# ── identity_tier: 우선순위 c_level > engineering > general ──
def test_tier_c_level_from_role():
    assert identity_tier(["c_level"], []) == TIER_C_LEVEL


def test_tier_engineering_from_department():
    assert identity_tier([], ["engineering"]) == TIER_ENGINEERING


def test_tier_general_default():
    assert identity_tier([], ["sales"]) == TIER_GENERAL
    assert identity_tier([], []) == TIER_GENERAL


def test_tier_c_level_beats_engineering():
    # c_level이면서 engineering 부서라도 최상위 등급
    assert identity_tier(["c_level"], ["engineering"]) == TIER_C_LEVEL


def test_tier_engineering_beats_other_departments():
    # 교차부서(engineering + product)는 engineering 등급
    assert identity_tier([], ["product", "engineering"]) == TIER_ENGINEERING


# ── gate_lookup: ADR-0016 매트릭스 ──────────────────────────
def test_select_allowed_for_all_tiers():
    for tier in (TIER_GENERAL, TIER_ENGINEERING, TIER_C_LEVEL):
        decision, _ = gate_lookup(tier, RISK_SELECT)
        assert decision == DECISION_ALLOW


def test_bulk_select_justify_for_all_tiers():
    # ADR-0027: c_level도 면제 없이 사유 기재 — 최고 권한일수록 더 기록한다.
    assert gate_lookup(TIER_GENERAL, RISK_BULK_SELECT)[0] == DECISION_JUSTIFY_AND_APPROVE
    assert gate_lookup(TIER_ENGINEERING, RISK_BULK_SELECT)[0] == DECISION_JUSTIFY_AND_APPROVE
    assert gate_lookup(TIER_C_LEVEL, RISK_BULK_SELECT)[0] == DECISION_JUSTIFY_AND_APPROVE


def test_update_delete_matrix():
    assert gate_lookup(TIER_GENERAL, RISK_UPDATE_DELETE)[0] == DECISION_DENY
    assert gate_lookup(TIER_ENGINEERING, RISK_UPDATE_DELETE)[0] == DECISION_JUSTIFY_AND_APPROVE
    assert gate_lookup(TIER_C_LEVEL, RISK_UPDATE_DELETE)[0] == DECISION_JUSTIFY_AND_APPROVE


def test_ddl_denied_for_all_including_c_level():
    for tier in (TIER_GENERAL, TIER_ENGINEERING, TIER_C_LEVEL):
        assert gate_lookup(tier, RISK_DDL)[0] == DECISION_DENY


def test_risk_deny_always_denied():
    # 위험도 분류 폴백(DENY)은 어느 신원이든 차단
    for tier in (TIER_GENERAL, TIER_ENGINEERING, TIER_C_LEVEL):
        assert gate_lookup(tier, RISK_DENY)[0] == DECISION_DENY


def test_gate_lookup_returns_reason():
    decision, reason = gate_lookup(TIER_GENERAL, RISK_UPDATE_DELETE)
    assert decision == DECISION_DENY
    assert isinstance(reason, str) and reason   # 사유 비어있지 않음

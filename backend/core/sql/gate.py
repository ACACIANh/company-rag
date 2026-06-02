"""신원×위험도 게이트 매트릭스 (ADR-0016).

질문자의 신원 등급과 SQL 위험도(core.sql.risk)를 교차해 3-state 결정을 내린다.
LangGraph를 모르는 순수 정책 로직 — 신원 조회(FGA)·감사 기록은 노드의 책임이다.
"""
from core.sql.risk import (
    RISK_SELECT,
    RISK_BULK_SELECT,
    RISK_UPDATE_DELETE,
    RISK_DDL,
    RISK_DENY,
)

# 신원 등급 (기존 권한주체로 매핑 — 신규 권한주체 도입 없음)
TIER_GENERAL = "general"          # 특수 역할 없는 부서원
TIER_ENGINEERING = "engineering"  # 기술 부서원
TIER_C_LEVEL = "c_level"          # super_reader 역할

# 게이트 3-state
DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_NEEDS_APPROVAL = "NEEDS_APPROVAL"

# (신원, 위험도) → 결정. ADR-0016 권한 매트릭스.
_MATRIX = {
    RISK_SELECT: {
        TIER_GENERAL: DECISION_ALLOW,
        TIER_ENGINEERING: DECISION_ALLOW,
        TIER_C_LEVEL: DECISION_ALLOW,
    },
    RISK_BULK_SELECT: {
        TIER_GENERAL: DECISION_NEEDS_APPROVAL,
        TIER_ENGINEERING: DECISION_NEEDS_APPROVAL,
        TIER_C_LEVEL: DECISION_ALLOW,
    },
    RISK_UPDATE_DELETE: {
        TIER_GENERAL: DECISION_DENY,
        TIER_ENGINEERING: DECISION_NEEDS_APPROVAL,
        TIER_C_LEVEL: DECISION_NEEDS_APPROVAL,
    },
    RISK_DDL: {
        TIER_GENERAL: DECISION_DENY,
        TIER_ENGINEERING: DECISION_DENY,
        TIER_C_LEVEL: DECISION_DENY,
    },
    # 위험도 분류 폴백(파싱 실패·미지원)은 어느 신원이든 차단
    RISK_DENY: {
        TIER_GENERAL: DECISION_DENY,
        TIER_ENGINEERING: DECISION_DENY,
        TIER_C_LEVEL: DECISION_DENY,
    },
}


def identity_tier(roles: list[str], departments: list[str]) -> str:
    """신원 등급을 결정. 우선순위: c_level > engineering > general."""
    if TIER_C_LEVEL in roles:
        return TIER_C_LEVEL
    if TIER_ENGINEERING in departments:
        return TIER_ENGINEERING
    return TIER_GENERAL


def gate_lookup(tier: str, risk: str) -> tuple[str, str]:
    """(신원 등급, 위험도) → (결정, 사유). 미지의 조합은 보수적으로 DENY."""
    decision = _MATRIX.get(risk, {}).get(tier, DECISION_DENY)
    reason = f"신원={tier} × 위험도={risk} → {decision}"
    return decision, reason

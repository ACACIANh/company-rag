"""신원×위험도 게이트 매트릭스 (ADR-0016, 매트릭스 개정 ADR-0027).

질문자의 신원 등급과 SQL 위험도(core.sql.risk)를 교차해 3-state 결정을 내린다.
LangGraph를 모르는 순수 정책 로직 — 신원 조회(FGA)·감사 기록은 노드의 책임이다.

DBA 부재 전제(ADR-0027): 회색지대는 외부 결재 대기가 아니라, 질문자 본인이
사유를 남기고 자기책임으로 통과(JUSTIFY_AND_APPROVE)하는 self-service 흐름이다.
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

# 게이트 3-state (회색지대 명칭 개정 ADR-0027: NEEDS_APPROVAL → JUSTIFY_AND_APPROVE)
DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_JUSTIFY_AND_APPROVE = "JUSTIFY_AND_APPROVE"

# (신원, 위험도) → 결정. ADR-0016 권한 매트릭스(ADR-0027 개정).
_MATRIX = {
    RISK_SELECT: {
        TIER_GENERAL: DECISION_ALLOW,
        TIER_ENGINEERING: DECISION_ALLOW,
        TIER_C_LEVEL: DECISION_ALLOW,
    },
    RISK_BULK_SELECT: {
        # 최고 권한일수록 면제가 아니라 기록 — c_level도 PII는 사유 기재(ADR-0027).
        TIER_GENERAL: DECISION_JUSTIFY_AND_APPROVE,
        TIER_ENGINEERING: DECISION_JUSTIFY_AND_APPROVE,
        TIER_C_LEVEL: DECISION_JUSTIFY_AND_APPROVE,
    },
    RISK_UPDATE_DELETE: {
        TIER_GENERAL: DECISION_DENY,
        TIER_ENGINEERING: DECISION_JUSTIFY_AND_APPROVE,
        TIER_C_LEVEL: DECISION_JUSTIFY_AND_APPROVE,
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

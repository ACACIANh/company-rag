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

"""capability 게이트 (ADR-0028, 3-state 의미 ADR-0027 유지).

SQL 위험도(core.sql.risk)를 OpenFGA capability:sql 의 2층 relation
(allow_*/justify_*) Check로 교차해 3-state 결정을 내린다. 게이트 정책은
코드 매트릭스가 아니라 OpenFGA 튜플에 있다 — 신원 조회·감사 기록은 노드의 책임이다.

DBA 부재 전제(ADR-0027): 회색지대는 외부 결재 대기가 아니라, 질문자 본인이
사유를 남기고 자기책임으로 통과(JUSTIFY_AND_APPROVE)하는 self-service 흐름이다.
"""
from typing import Awaitable, Callable

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

# allow_* 없이 justify_* 만 허용하는 위험도(매트릭스 정리). 단순 SELECT만 즉시 허용(allow_select)이고
# 그 외 모든 위험군(BULK_SELECT·UPDATE/DELETE·DDL·GRANT)은 사유 기재 후 실행 — 이력에 남긴다.
# allow_* relation을 모델에서 제거했으므로 allow Check 자체를 건너뛴다(undefined-relation 에러 방지).
_JUSTIFY_ONLY_RISKS = frozenset({
    RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL, RISK_GRANT,
})


async def gate_decision(
    check: Callable[[str, str, str], Awaitable[bool]],
    user_id: str,
    risk: str,
) -> tuple[str, str]:
    """(check, user_id, 위험도) → (결정, 사유).

    allow_<base>@<obj> 보유 → ALLOW, 없으면 justify_<base>@<obj> 보유 →
    JUSTIFY_AND_APPROVE, 둘 다 없으면 DENY. 미지원 위험도는 보수적으로 DENY.
    _JUSTIFY_ONLY_RISKS 에 속하는 위험도는 allow 체크를 건너뛴다.
    """
    entry = _RISK_GATE.get(risk)
    if entry is None:
        return DECISION_DENY, f"위험도={risk} 미지원 → DENY"
    obj, base = entry
    user = f"user:{user_id}"
    if risk not in _JUSTIFY_ONLY_RISKS and await check(user, f"allow_{base}", obj):
        return DECISION_ALLOW, f"capability allow_{base}@{obj} 보유 → ALLOW"
    if await check(user, f"justify_{base}", obj):
        return DECISION_JUSTIFY_AND_APPROVE, f"capability justify_{base}@{obj} 보유 → JUSTIFY_AND_APPROVE"
    return DECISION_DENY, f"capability {base}@{obj} 미부여 → DENY"

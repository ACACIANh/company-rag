"""신원×위험도 게이트 노드 (ADR-0016).

FGA로 질문자의 신원(역할·부서)을 권위 소스에서 조회해 등급을 정하고, 위험도
(ADR-0017)와 교차해 3-state 결정을 내린다. 신원을 JWT가 아니라 FGA에서 읽는
이유: 권한 회수(부서 제외·역할 강등)가 즉시 반영되어야 하기 때문(ADR-0016).
모든 결정은 감사 로그(ADR-0018)에 남긴다.
"""
from core.fga.client import FGAClient
from core.observability.audit.base import AuditRecord, AuditSink
from core.sql.gate import identity_tier, gate_lookup


async def gate_node(state: dict, *, fga_client: FGAClient, audit_sink: AuditSink) -> dict:
    user_id = state["user_id"]
    roles = await fga_client.user_roles(user_id)
    departments = await fga_client.user_departments(user_id)
    tier = identity_tier(roles, departments)

    risk = state["sql_risk"]
    decision, reason = gate_lookup(tier, risk)

    await audit_sink.record(AuditRecord(
        user_id=user_id,
        department=",".join(departments),
        role=",".join(roles),
        question=state.get("question", ""),
        generated_sql=state.get("generated_sql", ""),
        sql_risk=risk,
        gate_decision=decision,
        reason=reason,
        result_summary="",
        thread_id=state.get("thread_id", ""),
    ))
    return {"gate_decision": decision}

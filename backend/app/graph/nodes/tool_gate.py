"""도구-실행-전 게이트 인터셉터 (ADR-0023).

에이전트가 부른 각 도구 호출을 plan으로 구체화(SQL의 경우 생성된 SQL+위험도)한 뒤,
신원×위험도 게이트(core.sql.gate)로 ALLOW/JUSTIFY/DENY를 판정한다. ALLOW는 즉시
실행해 ToolMessage를 만들고, DENY는 실행 없이 거부 ToolMessage를, JUSTIFY는
pending_tool_calls에 적재만 한다(HITL은 confirm/justify_execute에서). 모든 결정은
감사 로그(ADR-0018)에 남긴다.
"""
from langchain_core.messages import AIMessage, ToolMessage

from core.fga.client import FGAClient
from core.observability.audit.base import AuditRecord, AuditSink
from app.graph.tools._utils import normalize_sql
from app.graph.tools.permission_tool import delegated_membership_dept, delegated_permission
from core.sql.gate import (
    gate_decision,
    gate_table_access,
    RISK_GRANT,
    DECISION_ALLOW, DECISION_DENY, DECISION_JUSTIFY_AND_APPROVE,
)
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL
from core.sql.tables import extract_tables

# 테이블별 접근 게이트(ADR-0047)를 적용할 SQL 위험도 — query_business_data 경로만.
_SQL_RISKS = frozenset({RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, RISK_DDL})

_DENY_TEXT = "거부됨: 현재 권한으로 실행할 수 없는 요청입니다."
_ALREADY_EXECUTED_TEXT = "이미 실행 완료된 SQL입니다. 동일한 작업을 중복 실행하지 않습니다."


def _last_tool_calls(messages: list) -> tuple[AIMessage | None, list]:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return m, m.tool_calls
    return None, []


async def tool_gate_node(state: dict, *, registry, fga_client: FGAClient, audit_sink: AuditSink) -> dict:
    user_id = state["user_id"]
    roles = await fga_client.user_roles(user_id)
    departments = await fga_client.user_departments(user_id)

    _, tool_calls = _last_tool_calls(state.get("agent_messages") or [])
    executed_sql: set[str] = {normalize_sql(s) for s in (state.get("executed_sql") or [])}
    new_messages: list = []
    pending: list = []

    for tc in tool_calls:
        handler = registry.handlers.get(tc["name"])
        if handler is None:
            new_messages.append(ToolMessage(content="알 수 없는 도구", tool_call_id=tc["id"]))
            continue
        planned_action, risk = handler.plan({**tc["args"], "__caller_id": user_id})

        if normalize_sql(planned_action) in executed_sql:
            new_messages.append(ToolMessage(content=_ALREADY_EXECUTED_TEXT, tool_call_id=tc["id"]))
            continue

        decision, reason = await gate_decision(fga_client.check, user_id, risk)

        # 테이블별 접근 게이트(ADR-0047): SQL 위험도가 통과(ALLOW/JUSTIFY)했어도, 참조 테이블의
        # can_access를 추가로 AND한다. 하나라도 미보유면 최종 DENY로 강등(위험도×테이블 직교 결합).
        if decision in (DECISION_ALLOW, DECISION_JUSTIFY_AND_APPROVE) and risk in _SQL_RISKS:
            ok, table_reason = await gate_table_access(
                fga_client.check, user_id, extract_tables(planned_action)
            )
            if not ok:
                decision, reason = DECISION_DENY, table_reason

        # 권한 위임 승격: 전역 grant 권한 없는 DENY를, 부서 admin이면 JUSTIFY_AND_APPROVE로.
        if decision == DECISION_DENY and risk == RISK_GRANT:
            # (1) 부서 멤버십 위임 (ADR-0046)
            dept = delegated_membership_dept(planned_action)
            if dept and await fga_client.check(f"user:{user_id}", "admin", f"department:{dept}"):
                decision = DECISION_JUSTIFY_AND_APPROVE
                reason = f"부서 admin 멤버십 위임(department:{dept}) → JUSTIFY_AND_APPROVE"
            else:
                # (2) permission 배정 위임 (ADR-0051): 자기 부서가 holder인 permission을 개인에 배정
                perm = delegated_permission(planned_action)
                if perm:
                    for d in departments:
                        if (await fga_client.check(f"user:{user_id}", "admin", f"department:{d}")
                                and await fga_client.check(f"department:{d}#member", "holder", f"permission:{perm}")):
                            decision = DECISION_JUSTIFY_AND_APPROVE
                            reason = f"부서 admin permission 위임(department:{d}→permission:{perm}) → JUSTIFY_AND_APPROVE"
                            break

        if decision == DECISION_ALLOW:
            result = await handler.execute(planned_action, risk)
            new_messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
            result_summary = str(result)[:200]
        elif decision == DECISION_DENY:
            new_messages.append(ToolMessage(content=_DENY_TEXT, tool_call_id=tc["id"]))
            result_summary = ""
        else:  # JUSTIFY_AND_APPROVE
            pending.append({
                "id": tc["id"], "name": tc["name"], "args": tc["args"],
                "planned_action": planned_action, "risk": risk, "decision": decision,
            })
            result_summary = ""

        await audit_sink.record(AuditRecord(
            user_id=user_id,
            department=",".join(departments),
            role=",".join(roles),
            question=state.get("question", ""),
            generated_sql=planned_action,
            sql_risk=risk,
            gate_decision=decision,
            reason=reason,
            result_summary=result_summary,
            thread_id=state.get("thread_id", ""),
        ))

    out: dict = {}
    if new_messages:
        out["agent_messages"] = new_messages
    out["pending_tool_calls"] = pending

    # 단일 도구 호출 결과가 권한 스냅샷이면 LLM 재해석 없이 직접 answer로 사용.
    # (복수 도구 호출은 LLM 종합이 필요하므로 제외)
    if (
        not pending
        and len(tool_calls) == 1
        and len(new_messages) == 1
        and isinstance(new_messages[0].content, str)
        and new_messages[0].content.startswith("## 권한 스냅샷")
    ):
        out["answer"] = new_messages[0].content

    return out

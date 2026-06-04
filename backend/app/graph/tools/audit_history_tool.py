"""감사 이력 조회 에이전트 (ADR-0040). 관리자 전용 gate_audit_log 조회.

plan()은 LLM 인자를 검증해 params_json + RISK_SELECT를 반환한다.
execute()는 FGA admin 역할 확인 후 gate_audit_log를 SELECT한다.
caller_id는 tool_gate_node가 __caller_id 키로 주입한다.
"""
import json

import asyncpg
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from core.fga.client import FGAClient
from core.sql.risk import RISK_DENY, RISK_SELECT

_VALID_DECISIONS = frozenset({"ALLOW", "DENY", "JUSTIFY_AND_APPROVE"})
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_DESCRIPTION = (
    "감사 이력(게이트 결정·SQL 실행 사유)을 조회합니다. 관리자 전용. "
    "limit(건수 기본 20 최대 100), user_id(유저 필터), "
    "decision(ALLOW/DENY/JUSTIFY_AND_APPROVE), "
    "start_date/end_date(YYYY-MM-DD) 인자를 조합해 최신순으로 반환합니다."
)

_QUERY = (
    "SELECT user_id, department, role, question, generated_sql, sql_risk, "
    "gate_decision, reason, result_summary, created_at "
    "FROM gate_audit_log "
    "WHERE ($1::text IS NULL OR user_id = $1) "
    "  AND ($2::text IS NULL OR gate_decision = $2) "
    "  AND ($3::date IS NULL OR created_at::date >= $3::date) "
    "  AND ($4::date IS NULL OR created_at::date <= $4::date) "
    "ORDER BY created_at DESC LIMIT $5"
)


class _Input(BaseModel):
    limit: int = Field(default=_DEFAULT_LIMIT, description="반환 건수 (최대 100)")
    user_id: str | None = Field(default=None, description="특정 유저 ID 필터")
    decision: str | None = Field(
        default=None, description="ALLOW / DENY / JUSTIFY_AND_APPROVE"
    )
    start_date: str | None = Field(default=None, description="시작 날짜 YYYY-MM-DD")
    end_date: str | None = Field(default=None, description="종료 날짜 YYYY-MM-DD")


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    header = "| 시각 | 유저 | 부서/역할 | 결정 | SQL | 사유 | 결과요약 |"
    sep    = "|---|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        ts = str(r["created_at"])[:16]
        dept_role = f"{r['department'] or ''} / {r['role'] or ''}".strip(" /")
        sql_preview = str(r["generated_sql"])[:50].replace("|", "\\|")
        result_preview = str(r["result_summary"] or "")[:50].replace("|", "\\|")
        reason = str(r["reason"] or "").replace("|", "\\|")
        lines.append(
            f"| {ts} | {r['user_id']} | {dept_role} | {r['gate_decision']} | "
            f"`{sql_preview}` | {reason} | {result_preview} |"
        )
    return "\n".join(lines)


class AuditAgent:
    name = "query_audit_history"

    def __init__(self, *, fga_client: FGAClient, app_pool: asyncpg.Pool) -> None:
        self._fga = fga_client
        self._pool = app_pool
        self.tool = StructuredTool.from_function(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda **_: "",
            args_schema=_Input,
        )

    def plan(self, args: dict) -> tuple[str, str]:
        caller_id = args.get("__caller_id", "")
        try:
            limit = min(int(args.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT
        decision = args.get("decision")
        if decision is not None and decision not in _VALID_DECISIONS:
            return f"잘못된 decision 값: {decision!r}", RISK_DENY
        params = {
            "caller_id": caller_id,
            "limit": limit,
            "user_id": args.get("user_id"),
            "decision": decision,
            "start_date": args.get("start_date"),
            "end_date": args.get("end_date"),
        }
        return json.dumps(params, ensure_ascii=False), RISK_SELECT

    async def execute(self, planned_action: str, risk: str) -> str:
        try:
            params = json.loads(planned_action)
        except Exception:
            return "감사 이력 조회 오류: 파라미터 파싱 실패"
        caller_id = params.get("caller_id", "")
        if not caller_id:
            return "권한 없음: 감사 이력은 관리자만 조회할 수 있습니다."
        try:
            has_access = await self._fga.check(
                f"user:{caller_id}", "justify_grant", "capability:admin"
            )
        except Exception:
            return "권한 없음: 역할 조회 실패"
        if not has_access:
            return "권한 없음: 감사 이력은 관리자만 조회할 수 있습니다."
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    _QUERY,
                    params.get("user_id"),
                    params.get("decision"),
                    params.get("start_date"),
                    params.get("end_date"),
                    params.get("limit", _DEFAULT_LIMIT),
                )
            return _format_rows(list(rows))
        except Exception as exc:
            return f"감사 이력 조회 오류: {type(exc).__name__}"

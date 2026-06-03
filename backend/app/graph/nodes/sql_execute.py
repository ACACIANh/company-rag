"""SQL 실행 노드 (ADR-0016 — ALLOW/승인 경로 전용).

게이트가 통과시킨 SQL만 여기 도달한다. read-only 제한계정(sql_tool_ro,
ADR-0020) 풀로 실행하므로, 설사 쓰기 SQL이 잘못 흘러와도 계정 권한이 차단한다
(심층 방어). 결과는 generate가 해석하도록 documents에 싣고, 실행 결과를 감사
로그(ADR-0018)에 남긴다. 실행 오류는 잡아서 결과로 변환한다 — 게이트 경로가
예외로 끊기지 않도록.
"""
import asyncpg

from core.models import Chunk, SearchResult
from core.observability.audit.base import AuditRecord, AuditSink

_DEFAULT_ROW_LIMIT = 100


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join(str(r[c]) for c in cols))
    return "\n".join(lines)


async def sql_execute_node(
    state: dict,
    *,
    sql_pool: asyncpg.Pool,
    audit_sink: AuditSink,
    row_limit: int = _DEFAULT_ROW_LIMIT,
) -> dict:
    sql = state["generated_sql"]
    try:
        async with sql_pool.acquire() as conn:
            rows = await conn.fetch(sql)
        limited = list(rows)[:row_limit]
        text = _format_rows(limited)
        result_summary = f"{len(limited)} rows"
    except Exception as exc:
        text = f"SQL 실행 오류: {type(exc).__name__}"
        result_summary = text

    await audit_sink.record(AuditRecord(
        user_id=state["user_id"],
        department="",
        role="",
        question=state.get("question", ""),
        generated_sql=sql,
        sql_risk=state.get("sql_risk", ""),
        gate_decision=state.get("gate_decision", ""),
        # JUSTIFY_AND_APPROVE 경로면 본인이 기재한 사유를, ALLOW 경로면 실행 표식을 남긴다(ADR-0027).
        reason=state.get("justification") or "execution",
        result_summary=result_summary,
        thread_id=state.get("thread_id", ""),
    ))

    result = SearchResult(
        chunk=Chunk(text=text, source="sql-tool", chunk_id="sql-0"),
        score=1.0,
    )
    return {"documents": [result]}

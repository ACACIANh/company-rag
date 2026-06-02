"""PostgreSQL append-only 감사 로그 sink (ADR-0018).

게이트 결정·실행 결과를 단일 Postgres의 gate_audit_log 테이블에 INSERT만 한다.
UPDATE/DELETE를 제공하지 않아(append-only) 감사 기록의 무결성을 지킨다.
SQL 도구의 대상 DB(business 스키마)가 아닌 운영 DB(app)에 두어 자기 위변조를 막는다.
"""
import asyncpg

from core.observability.audit.base import AuditRecord, AuditSink


class PostgresAuditSink(AuditSink):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS gate_audit_log (
                    id             BIGSERIAL PRIMARY KEY,
                    user_id        TEXT NOT NULL,
                    department     TEXT,
                    role           TEXT,
                    question       TEXT,
                    generated_sql  TEXT,
                    sql_risk       TEXT,
                    gate_decision  TEXT,
                    reason         TEXT,
                    result_summary TEXT,
                    thread_id      TEXT,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)

    async def record(self, record: AuditRecord) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO gate_audit_log "
                "(user_id, department, role, question, generated_sql, sql_risk, "
                "gate_decision, reason, result_summary, thread_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                record.user_id,
                record.department,
                record.role,
                record.question,
                record.generated_sql,
                record.sql_risk,
                record.gate_decision,
                record.reason,
                record.result_summary,
                record.thread_id,
            )

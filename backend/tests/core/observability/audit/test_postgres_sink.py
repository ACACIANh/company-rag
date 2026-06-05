from unittest.mock import AsyncMock, MagicMock

import pytest

from core.observability.audit.base import AuditRecord
from core.observability.audit.postgres_sink import PostgresAuditSink


def _make_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


def _record(**overrides) -> AuditRecord:
    base = dict(
        user_id="user-joohwan",
        department="개발",
        role="member",
        question="전직원 급여 보여줘",
        generated_sql="SELECT salary FROM business.employees",
        sql_risk="bulk_select",
        gate_decision="JUSTIFY_AND_APPROVE",
        reason="대량/PII SELECT, engineering",
        result_summary="",
        thread_id="thread-1",
    )
    base.update(overrides)
    return AuditRecord(**base)


# ── AuditRecord 구조 ────────────────────────────────────────
def test_audit_record_has_gate_fields():
    r = _record()
    assert r.user_id == "user-joohwan"
    assert r.sql_risk == "bulk_select"
    assert r.gate_decision == "JUSTIFY_AND_APPROVE"
    assert r.thread_id == "thread-1"


# ── ensure_table ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ensure_table_creates_table():
    pool, conn = _make_pool()
    sink = PostgresAuditSink(pool)
    await sink.ensure_table()
    sql = conn.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS gate_audit_log" in sql


# ── record: append-only INSERT ──────────────────────────────
@pytest.mark.asyncio
async def test_record_inserts():
    pool, conn = _make_pool()
    sink = PostgresAuditSink(pool)
    await sink.record(_record())
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert sql.strip().upper().startswith("INSERT INTO GATE_AUDIT_LOG")


@pytest.mark.asyncio
async def test_record_is_append_only_never_mutates():
    pool, conn = _make_pool()
    sink = PostgresAuditSink(pool)
    await sink.record(_record())
    sql = conn.execute.call_args[0][0].upper()
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


@pytest.mark.asyncio
async def test_record_passes_all_fields_as_params():
    pool, conn = _make_pool()
    sink = PostgresAuditSink(pool)
    rec = _record()
    await sink.record(rec)
    args = conn.execute.call_args[0][1:]   # SQL 뒤의 바인딩 파라미터
    assert rec.user_id in args
    assert rec.generated_sql in args
    assert rec.gate_decision in args
    assert rec.thread_id in args


def _make_pool_with_fetch(rows):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=None),
    ))
    return pool, conn


@pytest.mark.asyncio
async def test_count_by_decision_groups_by_decision():
    rows = [
        {"gate_decision": "ALLOW", "n": 15},
        {"gate_decision": "DENY", "n": 3},
        {"gate_decision": "JUSTIFY_AND_APPROVE", "n": 5},
    ]
    pool, conn = _make_pool_with_fetch(rows)
    sink = PostgresAuditSink(pool)

    counts = await sink.count_by_decision()

    assert counts == {"ALLOW": 15, "DENY": 3, "JUSTIFY_AND_APPROVE": 5}
    sql = conn.fetch.call_args[0][0].upper()
    assert "GROUP BY GATE_DECISION" in sql
    assert "FROM GATE_AUDIT_LOG" in sql


@pytest.mark.asyncio
async def test_count_by_decision_empty_returns_empty_dict():
    pool, _ = _make_pool_with_fetch([])
    sink = PostgresAuditSink(pool)
    assert await sink.count_by_decision() == {}

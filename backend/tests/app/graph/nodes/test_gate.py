from unittest.mock import AsyncMock

import pytest

from app.graph.nodes.gate import gate_node
from core.sql.gate import DECISION_DENY, DECISION_JUSTIFY_AND_APPROVE


def _fga(roles, departments):
    fga = AsyncMock()
    fga.user_roles = AsyncMock(return_value=roles)
    fga.user_departments = AsyncMock(return_value=departments)
    return fga


def _state(risk, **over):
    base = {
        "user_id": "user-x",
        "sql_risk": risk,
        "question": "q",
        "generated_sql": "SELECT 1",
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_general_update_delete_denied():
    fga = _fga(roles=[], departments=["sales"])
    audit = AsyncMock()
    result = await gate_node(_state("update_delete"), fga_client=fga, audit_sink=audit)
    assert result["gate_decision"] == DECISION_DENY


@pytest.mark.asyncio
async def test_engineering_bulk_select_justify():
    fga = _fga(roles=[], departments=["engineering"])
    audit = AsyncMock()
    result = await gate_node(_state("bulk_select"), fga_client=fga, audit_sink=audit)
    assert result["gate_decision"] == DECISION_JUSTIFY_AND_APPROVE


@pytest.mark.asyncio
async def test_c_level_bulk_select_justify():
    # ADR-0027: c_level의 대량/PII 읽기도 ALLOW가 아니라 사유 기재.
    fga = _fga(roles=["c_level"], departments=[])
    audit = AsyncMock()
    result = await gate_node(_state("bulk_select"), fga_client=fga, audit_sink=audit)
    assert result["gate_decision"] == DECISION_JUSTIFY_AND_APPROVE


@pytest.mark.asyncio
async def test_records_audit_with_decision_and_identity():
    fga = _fga(roles=["c_level"], departments=["engineering"])
    audit = AsyncMock()
    await gate_node(_state("ddl"), fga_client=fga, audit_sink=audit)
    audit.record.assert_awaited_once()
    rec = audit.record.call_args[0][0]
    assert rec.user_id == "user-x"
    assert rec.gate_decision == DECISION_DENY     # DDL → 전계층 DENY
    assert rec.sql_risk == "ddl"
    assert "c_level" in rec.role


@pytest.mark.asyncio
async def test_queries_fga_for_identity():
    fga = _fga(roles=[], departments=["engineering"])
    audit = AsyncMock()
    await gate_node(_state("select"), fga_client=fga, audit_sink=audit)
    fga.user_roles.assert_awaited_once_with("user-x")
    fga.user_departments.assert_awaited_once_with("user-x")

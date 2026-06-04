from unittest.mock import AsyncMock, MagicMock

import pytest

from app.graph.tools.permission_tool import PermissionToolHandler
from core.fga.permission_validator import PermissionValidator
from core.sql.gate import RISK_GRANT
from core.sql.risk import RISK_DENY


def _validator():
    return PermissionValidator(
        user_ids={"user-alice"}, departments={"engineering"}, folders={"/company"}
    )


def _llm(reply: str):
    llm = MagicMock()
    llm.complete.return_value = reply
    return llm


def test_plan_valid_grant_returns_risk_grant():
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"instruction": "alice를 engineering에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-alice member department:engineering"


def test_plan_invalid_target_returns_deny():
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-eve","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "eve를 추가"})
    assert risk == RISK_DENY


def test_plan_unparseable_llm_output_returns_deny():
    handler = PermissionToolHandler(
        llm=_llm("죄송하지만 도와드릴 수 없습니다"),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "이상한 지시"})
    assert risk == RISK_DENY


def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 instruction을 추출한다 (ADR-0032)."""
    handler = PermissionToolHandler(
        llm=_llm('{"action":"grant","subject":"user:user-alice","relation":"member","object":"department:engineering"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"__arg1": "alice를 engineering에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-alice member department:engineering"


@pytest.mark.asyncio
async def test_execute_grant_calls_grant_tuple():
    fga = MagicMock()
    fga.grant_tuple = AsyncMock()
    handler = PermissionToolHandler(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await handler.execute("grant user:user-alice member department:engineering", "RISK_GRANT")
    fga.grant_tuple.assert_awaited_once_with("user:user-alice", "member", "department:engineering")
    assert "완료" in result


@pytest.mark.asyncio
async def test_execute_revoke_calls_revoke_tuple():
    fga = MagicMock()
    fga.revoke_tuple = AsyncMock()
    handler = PermissionToolHandler(llm=MagicMock(), fga_client=fga, validator=_validator())
    await handler.execute("revoke user:user-alice member department:engineering", "RISK_GRANT")
    fga.revoke_tuple.assert_awaited_once_with("user:user-alice", "member", "department:engineering")

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.graph.tools.permission_tool as pt
from app.graph.tools.base import ToolResult
from app.graph.tools.permission_tool import (
    PermissionAgent,
    delegated_membership_dept,
    delegated_permission,
    _format_permission_snapshot,
    _resolve_capabilities,
)
from core.fga.permission_validator import PermissionValidator
from core.sql.gate import RISK_GRANT
from core.sql.risk import RISK_DENY


class _ConcurrencyProbe:
    """동시 in-flight 최대치(peak)를 기록 — 병렬이면 peak==N, 순차면 1."""

    def __init__(self) -> None:
        self.cur = 0
        self.peak = 0

    async def run(self, value):
        self.cur += 1
        self.peak = max(self.peak, self.cur)
        for _ in range(4):
            await asyncio.sleep(0)
        self.cur -= 1
        return value


def _validator():
    return PermissionValidator(
        user_ids={"user-joohwan", "user-minjun"},
        departments={"개발"},
        permissions={"기본"},
        names={"노주환": "user-joohwan", "이민준": "user-minjun"},
    )


def _llm(reply: str):
    llm = MagicMock()
    llm.complete.return_value = reply
    return llm


def test_delegated_membership_dept_grant():
    assert delegated_membership_dept("grant user:user-joohwan member department:개발") == "개발"


def test_delegated_membership_dept_revoke():
    assert delegated_membership_dept("revoke user:user-minjun member department:인사") == "인사"


def test_delegated_membership_dept_non_membership_none():
    # permission 배정·capability는 멤버십 위임 대상이 아니다 → None.
    assert delegated_membership_dept("grant user:user-joohwan holder permission:개발") is None
    assert delegated_membership_dept("grant user:user-joohwan justify_select capability:sql") is None


def test_delegated_membership_dept_malformed_none():
    assert delegated_membership_dept("query u1 u2") is None
    assert delegated_membership_dept("grant user:x member role:c_level") is None
    assert delegated_membership_dept("") is None


def test_plan_valid_grant_returns_risk_grant():
    handler = PermissionAgent(
        llm=_llm('{"action":"grant","subject":"user:user-joohwan","relation":"member","object":"department:개발"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"instruction": "노주환를 개발에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-joohwan member department:개발"


def test_plan_invalid_target_returns_deny():
    handler = PermissionAgent(
        llm=_llm('{"action":"grant","subject":"user:user-eve","relation":"member","object":"department:개발"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "eve를 추가"})
    assert risk == RISK_DENY


def test_plan_unparseable_llm_output_returns_deny():
    handler = PermissionAgent(
        llm=_llm("죄송하지만 도와드릴 수 없습니다"),
        fga_client=MagicMock(), validator=_validator(),
    )
    _, risk = handler.plan({"instruction": "이상한 지시"})
    assert risk == RISK_DENY


def test_plan_accepts_arg1_key():
    """bind_tools가 넘기는 {'__arg1': ...} 형태에서도 instruction을 추출한다 (ADR-0032)."""
    handler = PermissionAgent(
        llm=_llm('{"action":"grant","subject":"user:user-joohwan","relation":"member","object":"department:개발"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = handler.plan({"__arg1": "노주환를 개발에 추가"})
    assert risk == RISK_GRANT
    assert planned == "grant user:user-joohwan member department:개발"


@pytest.mark.asyncio
async def test_execute_grant_calls_grant_tuple():
    fga = MagicMock()
    fga.grant_tuple = AsyncMock()
    handler = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await handler.execute("grant user:user-joohwan member department:개발", "RISK_GRANT")
    fga.grant_tuple.assert_awaited_once_with("user:user-joohwan", "member", "department:개발")
    assert result.text == "완료: grant user:user-joohwan member department:개발"
    assert result.summary == "완료: grant user:user-joohwan member department:개발"


@pytest.mark.asyncio
async def test_execute_revoke_calls_revoke_tuple():
    fga = MagicMock()
    fga.revoke_tuple = AsyncMock()
    handler = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await handler.execute("revoke user:user-joohwan member department:개발", "RISK_GRANT")
    fga.revoke_tuple.assert_awaited_once_with("user:user-joohwan", "member", "department:개발")
    assert isinstance(result, ToolResult)
    assert result.text == "완료: revoke user:user-joohwan member department:개발"
    assert result.summary == "완료: revoke user:user-joohwan member department:개발"


@pytest.mark.asyncio
async def test_execute_query_self_returns_snapshot():
    """본인 조회: caller == target → 부서/역할/폴더 + capability 스냅샷 (별도 admin 게이트 없음)."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["개발"])
    fga.user_roles = AsyncMock(return_value=["admin"])
    fga.get_readable_folders = AsyncMock(return_value=["/engineering/specs"])
    fga.user_accessible_tables = AsyncMock(return_value=["employees"])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-joohwan", "RISK_SELECT")
    assert "user-joohwan" in result.text
    assert "개발" in result.text
    assert "/engineering/specs" in result.text
    assert "SQL/관리 권한" in result.text
    assert result.summary == "권한 스냅샷 조회(user-joohwan)"


@pytest.mark.asyncio
async def test_execute_query_other_as_admin_succeeds():
    """타인 조회: caller != target, admin → 성공."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["제품"])
    fga.user_roles = AsyncMock(return_value=[])
    fga.get_readable_folders = AsyncMock(return_value=[])
    fga.user_accessible_tables = AsyncMock(return_value=[])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query admin-user user-minjun", "RISK_SELECT")
    fga.check.assert_any_await("user:admin-user", "justify_grant", "capability:admin")
    assert "user-minjun" in result.text


@pytest.mark.asyncio
async def test_execute_query_other_as_non_admin_denied():
    """타인 조회: caller != target, 비관리자 → 거부 메시지."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=False)
    fga.user_departments = MagicMock()
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-minjun", "RISK_SELECT")
    assert "권한 없음" in result.text
    assert result.summary == "권한 없음"
    fga.user_departments.assert_not_called()


def test_plan_query_self_returns_risk_select():
    """query 파싱 → RISK_SELECT, planned_action 형식 확인."""
    from core.sql.risk import RISK_SELECT
    agent = PermissionAgent(
        llm=_llm('{"action":"query","target_user_id":null}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = agent.plan({"instruction": "내 권한 알려줘", "__caller_id": "user-joohwan"})
    assert risk == RISK_SELECT
    assert planned == "query user-joohwan user-joohwan"


def test_plan_query_other_returns_risk_select():
    """타인 query도 plan 단계엔 RISK_SELECT (관리자 확인은 execute에서)."""
    from core.sql.risk import RISK_SELECT
    agent = PermissionAgent(
        llm=_llm('{"action":"query","target_user_id":"user-minjun"}'),
        fga_client=MagicMock(), validator=_validator(),
    )
    planned, risk = agent.plan({"instruction": "이민준 권한 알려줘", "__caller_id": "user-joohwan"})
    assert risk == RISK_SELECT
    assert planned == "query user-joohwan user-minjun"


@pytest.mark.asyncio
async def test_resolve_capabilities_maps_decisions_to_labels():
    """각 위험도를 gate_decision으로 판정 → 한국어 라벨 3종(즉시 허용/사유 기재 후 허용/불가)."""
    grants = {
        ("allow_select", "capability:sql"): True,            # SELECT → ALLOW
        ("justify_bulk_select", "capability:sql"): True,     # 대량 SELECT → JUSTIFY
        ("justify_update_delete", "capability:sql"): True,   # UPDATE/DELETE → JUSTIFY
        ("justify_ddl", "capability:sql"): False,            # DDL → DENY
        ("justify_grant", "capability:admin"): True,         # grant → JUSTIFY
    }

    async def fake_check(user, relation, object_):
        return grants.get((relation, object_), False)

    caps = await _resolve_capabilities(fake_check, "user-admin")
    assert caps == [
        ("SELECT", "즉시 허용"),
        ("대량 SELECT", "사유 기재 후 허용"),
        ("UPDATE/DELETE", "사유 기재 후 허용"),
        ("DDL", "불가"),
        ("권한 부여(grant)", "사유 기재 후 허용"),
    ]


def test_format_snapshot_renders_capability_section():
    """스냅샷에 'SQL/관리 권한' 섹션과 각 항목이 GFM 테이블 행으로 렌더링된다."""
    out = _format_permission_snapshot(
        "user-admin", [], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용"), ("DDL", "불가")],
    )
    assert "### SQL/관리 권한" in out
    assert "| SELECT | ✅ 즉시 허용 |" in out
    assert "| DDL | ❌ 불가 |" in out


def test_format_snapshot_markdown_headers():
    """마크다운 섹션 헤더(## 권한 스냅샷, ### 접근 가능 폴더, ### SQL/관리 권한)가 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", [], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용"), ("DDL", "불가")],
    )
    assert "## 권한 스냅샷" in out
    assert "### 접근 가능 폴더" in out
    assert "### SQL/관리 권한" in out


def test_format_snapshot_markdown_capability_table():
    """capability 섹션이 GFM 테이블 형식이고 이모지가 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", ["개발"], ["c_level"], [],
        [
            ("SELECT", "즉시 허용"),
            ("대량 SELECT", "사유 기재 후 허용"),
            ("DDL", "불가"),
        ],
    )
    assert "| SELECT | ✅ 즉시 허용 |" in out
    assert "| 대량 SELECT | ⚠️ 사유 기재 후 허용 |" in out
    assert "| DDL | ❌ 불가 |" in out
    # 테이블 헤더 행이 있다
    assert "| 작업 | 허용 여부 |" in out


def test_format_snapshot_renders_table_section():
    """스냅샷에 '### 접근 가능 테이블' 섹션이 포함된다."""
    out = _format_permission_snapshot(
        "user-admin", ["개발"], ["c_level"], ["/company"],
        [("SELECT", "즉시 허용")],
        tables=["employees", "sales"],
    )
    assert "### 접근 가능 테이블" in out
    assert "employees" in out
    assert "sales" in out


def test_format_snapshot_no_tables_shows_none():
    """테이블 접근권 없으면 '(없음)' 표시."""
    out = _format_permission_snapshot(
        "user-alice", [], [], [],
        [("SELECT", "즉시 허용")],
        tables=[],
    )
    assert "### 접근 가능 테이블" in out
    assert "(없음)" in out


@pytest.mark.asyncio
async def test_execute_query_includes_table_access():
    """query execute 결과에 테이블 접근 정보가 포함된다."""
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)
    fga.user_departments = AsyncMock(return_value=["개발"])
    fga.user_roles = AsyncMock(return_value=[])
    fga.get_readable_folders = AsyncMock(return_value=[])
    fga.user_accessible_tables = AsyncMock(return_value=["employees", "sales"])
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-joohwan", "RISK_SELECT")
    fga.user_accessible_tables.assert_awaited_once_with("user-joohwan")
    assert "employees" in result.text


def test_delegated_permission_grant_to_user():
    assert delegated_permission("grant user:user-minjun holder permission:인사") == "인사"


def test_delegated_permission_revoke_to_user():
    assert delegated_permission("revoke user:user-minjun holder permission:인사") == "인사"


def test_delegated_permission_to_department_none():
    # 부서 전체 배정(정의급)은 위임 대상 아님 → None (c_level 전용)
    assert delegated_permission("grant department:개발#member holder permission:개발") is None


def test_delegated_permission_non_holder_none():
    assert delegated_permission("grant user:user-joohwan member department:개발") is None
    assert delegated_permission("query u1 u2") is None


@pytest.mark.asyncio
async def test_execute_returns_toolresult_type():
    fga = MagicMock(); fga.grant_tuple = AsyncMock()
    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("grant user:u1 member department:개발", "RISK_GRANT")
    assert isinstance(result, ToolResult)


@pytest.mark.asyncio
async def test_resolve_capabilities_runs_concurrently(monkeypatch):
    """5개 위험도 gate_decision이 순차가 아닌 동시 실행돼야 한다(성능 회귀 가드).
    표시 순서(_CAPABILITY_DISPLAY)는 보존."""
    probe = _ConcurrencyProbe()

    async def fake_gate(check, user_id, risk):
        return await probe.run(("ALLOW", "reason"))

    monkeypatch.setattr(pt, "gate_decision", fake_gate)
    caps = await _resolve_capabilities(AsyncMock(), "user-admin")

    assert [label for label, _ in caps] == [
        "SELECT", "대량 SELECT", "UPDATE/DELETE", "DDL", "권한 부여(grant)",
    ]
    assert probe.peak == 5


@pytest.mark.asyncio
async def test_execute_query_snapshot_reads_run_concurrently(monkeypatch):
    """권한 스냅샷의 5개 독립 조회(부서·역할·폴더·capability·테이블)가 동시 실행돼야 한다."""
    probe = _ConcurrencyProbe()
    fga = MagicMock()
    fga.check = AsyncMock(return_value=True)

    async def _dep(t): return await probe.run(["개발"])
    async def _roles(t): return await probe.run([])
    async def _folders(t): return await probe.run([])
    async def _tables(t): return await probe.run(["employees"])
    fga.user_departments = _dep
    fga.user_roles = _roles
    fga.get_readable_folders = _folders
    fga.user_accessible_tables = _tables

    async def _caps(check, target): return await probe.run([("SELECT", "즉시 허용")])
    monkeypatch.setattr(pt, "_resolve_capabilities", _caps)

    agent = PermissionAgent(llm=MagicMock(), fga_client=fga, validator=_validator())
    result = await agent.execute("query user-joohwan user-joohwan", "RISK_SELECT")

    assert "user-joohwan" in result.text
    assert probe.peak == 5   # 5개 조회 동시 in-flight (순차면 1)

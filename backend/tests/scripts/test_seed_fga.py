import pytest
from unittest.mock import AsyncMock, MagicMock

from scripts.seed_fga import _build_tuples, _parent_of, _prune


def _find(tuples, **kw):
    return [t for t in tuples if all(t.get(k) == v for k, v in kw.items())]


# ── _parent_of ─────────────────────────────────────────────
def test_parent_of_nested():
    assert _parent_of("/company/engineering/ops") == "/company/engineering"


def test_parent_of_top_is_none():
    assert _parent_of("/company") is None


# ── 멤버십 튜플 ─────────────────────────────────────────────
def test_department_membership_tuple():
    tuples = _build_tuples([{"user_id": "user-jisoo", "departments": ["개발팀"]}], {})
    assert _find(tuples, user="user:user-jisoo", relation="member", object="department:개발팀")


def test_fga_role_membership_tuple():
    tuples = _build_tuples([{"user_id": "user-admin", "fga_roles": ["c_level"]}], {})
    assert _find(tuples, user="user:user-admin", relation="member", object="role:c_level")


def test_admin_jwt_role_gets_capability_admin_grant():
    tuples = _build_tuples([{"user_id": "user-admin", "roles": ["admin", "user"]}], {})
    assert _find(
        tuples, user="user:user-admin", relation="justify_grant", object="capability:admin"
    )


def test_non_admin_does_not_get_capability_admin_grant():
    tuples = _build_tuples([{"user_id": "user-jisoo", "roles": ["user"]}], {})
    assert not _find(tuples, user="user:user-jisoo", relation="justify_grant", object="capability:admin")


# ── 부서 관리자 위임(ADR-0046) ──────────────────────────────
def test_dept_admin_of_emits_admin_tuple():
    tuples = _build_tuples([{"user_id": "user-jisoo", "dept_admin_of": ["개발팀"]}], {})
    assert _find(tuples, user="user:user-jisoo", relation="admin", object="department:개발팀")


def test_no_dept_admin_of_emits_no_admin_tuple():
    tuples = _build_tuples([{"user_id": "user-seoyeon", "departments": ["영업팀"]}], {})
    assert not _find(tuples, user="user:user-seoyeon", relation="admin")


# ── 테이블 접근권(ADR-0047) ─────────────────────────────────
def test_table_grants_present():
    tuples = _build_tuples([], {})
    # c_level은 전 테이블, 인사팀은 employees, 영업팀은 sales.
    assert _find(tuples, user="role:c_level#member", relation="can_access", object="table:employees")
    assert _find(tuples, user="role:c_level#member", relation="can_access", object="table:sales")
    assert _find(tuples, user="department:인사팀#member", relation="can_access", object="table:employees")
    assert _find(tuples, user="department:영업팀#member", relation="can_access", object="table:sales")


def test_table_grants_respect_boundary():
    tuples = _build_tuples([], {})
    # 영업팀은 employees(PII) 접근권 없음 — 부서별 경계.
    assert not _find(tuples, user="department:영업팀#member", relation="can_access", object="table:employees")


# ── 폴더 권한 튜플 ──────────────────────────────────────────
def test_public_folder_tuple():
    tuples = _build_tuples([], {"/company": {"public": True}})
    assert _find(tuples, user="user:*", relation="public_viewer", object="folder:/company")


def test_private_folder_tuple():
    tuples = _build_tuples([], {"/company/hr": {"private": True}})
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/hr")


def test_dept_viewer_tuple():
    tuples = _build_tuples([], {"/company/hr": {"dept_viewers": ["hr"]}})
    assert _find(
        tuples, user="department:hr#member", relation="dept_viewer", object="folder:/company/hr"
    )


def test_super_reader_tuple():
    tuples = _build_tuples([], {"/company": {"super_readers": ["c_level"]}})
    assert _find(
        tuples, user="role:c_level#member", relation="super_reader", object="folder:/company"
    )


def test_parent_tuple_auto_derived():
    tuples = _build_tuples([], {"/company": {}, "/company/hr": {}})
    assert _find(tuples, user="folder:/company", relation="parent", object="folder:/company/hr")


# ── 회귀: 옛 'viewers' 키는 더 이상 dept_viewer 외 의미를 갖지 않음 ──
def test_no_legacy_viewer_relation_emitted():
    tuples = _build_tuples([], {"/company/hr": {"dept_viewers": ["hr"]}})
    assert not _find(tuples, relation="viewer")


# ── TechCorp 재구성: 신규 private 부서 폴더 ──────────────────
def test_finance_private_and_dept_viewer():
    folders = {"/company/finance": {"private": True, "dept_viewers": ["재무팀"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/finance")
    assert _find(
        tuples, user="department:재무팀#member", relation="dept_viewer",
        object="folder:/company/finance",
    )


def test_legal_private_and_dept_viewer():
    folders = {"/company/legal": {"private": True, "dept_viewers": ["법무팀"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/legal")
    assert _find(
        tuples, user="department:법무팀#member", relation="dept_viewer",
        object="folder:/company/legal",
    )


# ── _prune 재조정: config에 없는 stale 튜플만 삭제 ──────────────
@pytest.mark.asyncio
async def test_prune_deletes_only_stale():
    desired = [
        {"user": "user:user-jisoo", "relation": "member", "object": "department:개발팀"},
        {"user": "user:*", "relation": "public_viewer", "object": "folder:/company"},
    ]
    live = [
        ("user:user-jisoo", "member", "department:개발팀"),          # 유지(desired)
        ("user:*", "public_viewer", "folder:/company"),             # 유지
        ("user:user-minjun", "member", "department:hr"),            # stale(옛 부서)
        ("user:user-seoyeon", "allow_update_delete", "capability:sql"),  # stale(죽은 relation)
    ]
    client = MagicMock()
    client.list_all_tuples = AsyncMock(return_value=live)
    client.revoke_tuple = AsyncMock()

    stale = await _prune(client, desired)

    assert set(stale) == {
        ("user:user-minjun", "member", "department:hr"),
        ("user:user-seoyeon", "allow_update_delete", "capability:sql"),
    }
    assert client.revoke_tuple.await_count == 2
    client.revoke_tuple.assert_any_await("user:user-minjun", "member", "department:hr")
    # 유지 대상은 절대 삭제하지 않는다
    for u, r, o in [("user:user-jisoo", "member", "department:개발팀")]:
        assert ((u, r, o)) not in set(stale)


@pytest.mark.asyncio
async def test_prune_noop_when_live_matches_config():
    desired = [{"user": "user:a", "relation": "member", "object": "department:x"}]
    client = MagicMock()
    client.list_all_tuples = AsyncMock(return_value=[("user:a", "member", "department:x")])
    client.revoke_tuple = AsyncMock()

    stale = await _prune(client, desired)

    assert stale == []
    client.revoke_tuple.assert_not_awaited()

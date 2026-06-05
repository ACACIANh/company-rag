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
    tuples = _build_tuples([{"user_id": "user-jisoo", "departments": ["개발"]}], {}, {})
    assert _find(tuples, user="user:user-jisoo", relation="member", object="department:개발")


def test_fga_role_membership_tuple():
    tuples = _build_tuples([{"user_id": "user-admin", "fga_roles": ["c_level"]}], {}, {})
    assert _find(tuples, user="user:user-admin", relation="member", object="role:c_level")


def test_admin_jwt_role_gets_capability_admin_grant():
    tuples = _build_tuples([{"user_id": "user-admin", "roles": ["admin", "user"]}], {}, {})
    assert _find(
        tuples, user="user:user-admin", relation="justify_grant", object="capability:admin"
    )


def test_non_admin_does_not_get_capability_admin_grant():
    tuples = _build_tuples([{"user_id": "user-jisoo", "roles": ["user"]}], {}, {})
    assert not _find(tuples, user="user:user-jisoo", relation="justify_grant", object="capability:admin")


# ── 부서 관리자 위임(ADR-0046) ──────────────────────────────
def test_dept_admin_of_emits_admin_tuple():
    tuples = _build_tuples([{"user_id": "user-jisoo", "dept_admin_of": ["개발"]}], {}, {})
    assert _find(tuples, user="user:user-jisoo", relation="admin", object="department:개발")


def test_no_dept_admin_of_emits_no_admin_tuple():
    tuples = _build_tuples([{"user_id": "user-seoyeon", "departments": ["영업"]}], {}, {})
    assert not _find(tuples, user="user:user-seoyeon", relation="admin")


# ── 폴더 권한 튜플 ──────────────────────────────────────────
def test_public_folder_tuple():
    tuples = _build_tuples([], {"/company": {"public": True}}, {})
    assert _find(tuples, user="user:*", relation="public_viewer", object="folder:/company")


def test_private_folder_tuple():
    tuples = _build_tuples([], {"/company/hr": {"private": True}}, {})
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/hr")


def test_super_reader_tuple():
    tuples = _build_tuples([], {"/company": {"super_readers": ["c_level"]}}, {})
    assert _find(
        tuples, user="role:c_level#member", relation="super_reader", object="folder:/company"
    )


def test_parent_tuple_auto_derived():
    tuples = _build_tuples([], {"/company": {}, "/company/hr": {}}, {})
    assert _find(tuples, user="folder:/company", relation="parent", object="folder:/company/hr")


# ── permission 묶음(ADR-0051) ──────────────────────────────
_PERMS = {
    "기본": {"holders": ["user:*"], "sql": ["allow_select", "justify_bulk_select"]},
    "인사": {"holders": ["department:인사#member"], "folders": ["/company/hr"], "tables": ["employees"]},
    "개발": {"holders": ["department:개발#member"], "folders": ["/company/engineering/ops"],
             "tables": ["employees", "sales", "equipment"], "sql": ["justify_update_delete"]},
    "전사": {"holders": ["role:c_level#member"], "tables": ["employees", "sales", "equipment"],
             "sql": ["justify_update_delete"]},
}


def test_permission_holder_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="department:인사#member", relation="holder", object="permission:인사")
    assert _find(tuples, user="user:*", relation="holder", object="permission:기본")
    assert _find(tuples, user="role:c_level#member", relation="holder", object="permission:전사")


def test_permission_folder_gated_by_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="permission:인사", relation="gated_by", object="folder:/company/hr")


def test_permission_table_gated_by_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="permission:인사", relation="gated_by", object="table:employees")
    assert _find(tuples, user="permission:개발", relation="gated_by", object="table:equipment")


def test_permission_capability_tuple():
    tuples = _build_tuples([], {}, _PERMS)
    assert _find(tuples, user="permission:기본#holder", relation="allow_select", object="capability:sql")
    assert _find(tuples, user="permission:개발#holder", relation="justify_update_delete", object="capability:sql")


def test_table_boundary_via_permission():
    perms = {"영업": {"holders": ["department:영업#member"], "tables": ["sales"]}}
    tuples = _build_tuples([], {}, perms)
    assert _find(tuples, user="permission:영업", relation="gated_by", object="table:sales")
    assert not _find(tuples, user="permission:영업", relation="gated_by", object="table:employees")


def test_no_dept_viewer_relation_emitted():
    tuples = _build_tuples([{"user_id": "user-x", "departments": ["인사"]}], {"/company/hr": {"private": True}}, _PERMS)
    assert not _find(tuples, relation="dept_viewer")


# ── _prune 재조정: config에 없는 stale 튜플만 삭제 ──────────────
@pytest.mark.asyncio
async def test_prune_deletes_only_stale():
    desired = [
        {"user": "user:user-jisoo", "relation": "member", "object": "department:개발"},
        {"user": "user:*", "relation": "public_viewer", "object": "folder:/company"},
    ]
    live = [
        ("user:user-jisoo", "member", "department:개발"),          # 유지(desired)
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
    for u, r, o in [("user:user-jisoo", "member", "department:개발")]:
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

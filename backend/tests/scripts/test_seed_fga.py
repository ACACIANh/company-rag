from scripts.seed_fga import _build_tuples, _parent_of


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

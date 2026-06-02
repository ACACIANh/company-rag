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
    tuples = _build_tuples([{"user_id": "alice", "departments": ["engineering"]}], {})
    assert _find(tuples, user="user:alice", relation="member", object="department:engineering")


def test_fga_role_membership_tuple():
    tuples = _build_tuples([{"user_id": "admin", "fga_roles": ["c_level"]}], {})
    assert _find(tuples, user="user:admin", relation="member", object="role:c_level")


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
    # 신규 모델엔 'viewer' relation이 없다. dept_viewers로만 부서 권한을 표현.
    tuples = _build_tuples([], {"/company/hr": {"dept_viewers": ["hr"]}})
    assert not _find(tuples, relation="viewer")


# ── TechCorp 재구성: 신규 private 부서 폴더 ──────────────────
def test_finance_private_and_dept_viewer():
    folders = {"/company/finance": {"private": True, "dept_viewers": ["finance"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/finance")
    assert _find(
        tuples, user="department:finance#member", relation="dept_viewer",
        object="folder:/company/finance",
    )


def test_legal_private_and_dept_viewer():
    folders = {"/company/legal": {"private": True, "dept_viewers": ["legal"]}}
    tuples = _build_tuples([], folders)
    assert _find(tuples, user="user:*", relation="private_flag", object="folder:/company/legal")
    assert _find(
        tuples, user="department:legal#member", relation="dept_viewer",
        object="folder:/company/legal",
    )

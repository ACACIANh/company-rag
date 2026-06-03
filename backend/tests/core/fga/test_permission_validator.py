from core.fga.permission_validator import PermissionValidator

# 화이트리스트를 직접 주입(config 파일 비의존 단위 테스트)
def _validator():
    return PermissionValidator(
        user_ids={"user-alice", "user-bob"},
        departments={"engineering", "sales"},
        folders={"/company", "/company/finance"},
    )


def test_valid_department_member_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-alice",
                      "relation": "member", "object": "department:engineering"})
    assert tup == ("user:user-alice", "member", "department:engineering", "grant")


def test_valid_folder_viewer_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:engineering#member",
                      "relation": "dept_viewer", "object": "folder:/company/finance"})
    assert tup == ("department:engineering#member", "dept_viewer", "folder:/company/finance", "grant")


def test_valid_capability_grant_to_department():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:engineering#member",
                      "relation": "justify_update_delete", "object": "capability:sql"})
    assert tup == ("department:engineering#member", "justify_update_delete", "capability:sql", "grant")


def test_valid_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-bob",
                      "relation": "member", "object": "department:sales"})
    assert tup[3] == "revoke"


def test_reject_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "member", "object": "department:engineering"}) is None


def test_reject_unknown_department():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "member", "object": "department:marketing"}) is None


def test_reject_unknown_folder():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "department:engineering#member",
                       "relation": "dept_viewer", "object": "folder:/secret"}) is None


def test_reject_unknown_capability_relation():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "allow_drop_everything", "object": "capability:sql"}) is None


def test_reject_type_mismatch_member_to_folder():
    # member relation인데 object가 folder → 타입 정합 위반
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice",
                       "relation": "member", "object": "folder:/company"}) is None


def test_reject_bad_action():
    v = _validator()
    assert v.validate({"action": "delete_all", "subject": "user:user-alice",
                       "relation": "member", "object": "department:engineering"}) is None


def test_reject_whitespace_injection():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-alice x",
                       "relation": "member", "object": "department:engineering"}) is None


def test_catalog_text_contains_known_ids():
    v = _validator()
    text = v.catalog_text()
    assert "user-alice" in text and "engineering" in text and "/company/finance" in text

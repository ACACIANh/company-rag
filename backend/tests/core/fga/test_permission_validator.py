from core.fga.permission_validator import PermissionValidator

# 화이트리스트를 직접 주입(config 파일 비의존 단위 테스트)
def _validator():
    return PermissionValidator(
        user_ids={"user-jisoo", "user-minjun"},
        departments={"개발팀", "영업팀"},
        folders={"/company", "/company/finance"},
    )


def test_valid_department_member_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-jisoo",
                      "relation": "member", "object": "department:개발팀"})
    assert tup == ("user:user-jisoo", "member", "department:개발팀", "grant")


def test_valid_folder_viewer_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:개발팀#member",
                      "relation": "dept_viewer", "object": "folder:/company/finance"})
    assert tup == ("department:개발팀#member", "dept_viewer", "folder:/company/finance", "grant")


def test_valid_capability_grant_to_department():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:개발팀#member",
                      "relation": "justify_update_delete", "object": "capability:sql"})
    assert tup == ("department:개발팀#member", "justify_update_delete", "capability:sql", "grant")


def test_valid_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-minjun",
                      "relation": "member", "object": "department:영업팀"})
    assert tup[3] == "revoke"


def test_reject_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "member", "object": "department:개발팀"}) is None


def test_reject_unknown_department():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": "member", "object": "department:marketing"}) is None


def test_reject_unknown_folder():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "department:개발팀#member",
                       "relation": "dept_viewer", "object": "folder:/secret"}) is None


def test_reject_unknown_capability_relation():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": "allow_drop_everything", "object": "capability:sql"}) is None


def test_reject_removed_allow_capability_relations():
    # allow_bulk_select/allow_ddl은 매트릭스 정리로 모델에서 제거 — 더 이상 부여 불가(justify-only).
    v = _validator()
    for rel in ("allow_bulk_select", "allow_ddl"):
        assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                           "relation": rel, "object": "capability:sql"}) is None


def test_reject_type_mismatch_member_to_folder():
    # member relation인데 object가 folder → 타입 정합 위반
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": "member", "object": "folder:/company"}) is None


def test_reject_bad_action():
    v = _validator()
    assert v.validate({"action": "delete_all", "subject": "user:user-jisoo",
                       "relation": "member", "object": "department:개발팀"}) is None


def test_reject_whitespace_injection():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo x",
                       "relation": "member", "object": "department:개발팀"}) is None


def test_catalog_text_contains_known_ids():
    v = _validator()
    text = v.catalog_text()
    assert "user-jisoo" in text and "개발팀" in text and "/company/finance" in text


def test_reject_null_subject_no_crash():
    v = _validator()
    # LLM이 JSON null을 낸 경우 — 크래시 없이 None 반환(fail-closed)
    assert v.validate({"action": "grant", "subject": None,
                       "relation": "member", "object": "department:개발팀"}) is None


def test_reject_null_relation_no_crash():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": None, "object": "department:개발팀"}) is None

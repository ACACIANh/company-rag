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


# --- _resolve_user: 결정론적 사용자 참조 정규화 (ADR-0029/0031 후속) ---

def _resolver_validator():
    # 비격식 이름·접미 모호성 검증용 작은 카탈로그
    return PermissionValidator(
        user_ids={"user-alice", "user-bob", "user-team-bob"},
        departments={"개발팀"},
        folders={"/company"},
    )


def test_resolve_user_informal_name():
    # 비격식 단명 "alice" → 정식 "user:user-alice"
    v = _resolver_validator()
    assert v._resolve_user("alice") == "user:user-alice"


def test_resolve_user_bare_canonical_id():
    # 접두 없는 정식 id "user-alice" → "user:user-alice"
    v = _resolver_validator()
    assert v._resolve_user("user-alice") == "user:user-alice"


def test_resolve_user_already_canonical_with_prefix():
    # 이미 정식 "user:user-alice" → 그대로
    v = _resolver_validator()
    assert v._resolve_user("user:user-alice") == "user:user-alice"


def test_resolve_user_ambiguous_returns_none():
    # "bob"이 user-bob, user-team-bob 둘 다 endswith 매칭 → 모호 → None (fail-closed)
    v = _resolver_validator()
    assert v._resolve_user("bob") is None


def test_resolve_user_unknown_returns_none():
    # 카탈로그 밖 토큰 → None (화이트리스트 확장 금지)
    v = _resolver_validator()
    assert v._resolve_user("eve") is None
    assert v._resolve_user("user:user-eve") is None


def test_validate_member_grant_informal_subject():
    # 비격식 이름 subject "alice"가 member grant validate를 통과
    v = _resolver_validator()
    tup = v.validate({"action": "grant", "subject": "alice",
                      "relation": "member", "object": "department:개발팀"})
    assert tup == ("user:user-alice", "member", "department:개발팀", "grant")


def test_validate_member_grant_canonical_subject_still_passes():
    # 이미 정식 입력은 여전히 통과 (기존 동작 보존)
    v = _resolver_validator()
    tup = v.validate({"action": "grant", "subject": "user:user-bob",
                      "relation": "member", "object": "department:개발팀"})
    assert tup == ("user:user-bob", "member", "department:개발팀", "grant")


def test_validate_member_grant_ambiguous_subject_denied():
    # 모호한 subject "bob"은 여전히 None (RISK_DENY)
    v = _resolver_validator()
    assert v.validate({"action": "grant", "subject": "bob",
                       "relation": "member", "object": "department:개발팀"}) is None


def test_validate_member_grant_unknown_subject_denied():
    v = _resolver_validator()
    assert v.validate({"action": "grant", "subject": "eve",
                       "relation": "member", "object": "department:개발팀"}) is None


def test_validate_capability_grant_informal_user_subject():
    # capability 분기의 user subject도 비격식 이름 해석
    v = _resolver_validator()
    tup = v.validate({"action": "grant", "subject": "alice",
                      "relation": "justify_update_delete", "object": "capability:sql"})
    assert tup == ("user:user-alice", "justify_update_delete", "capability:sql", "grant")


# ── 테이블 dept_viewer 케이스 (ADR-0047, dept_viewer 단일 relation) ──────────────

def _table_validator():
    return PermissionValidator(
        user_ids={"user-jisoo", "user-minjun"},
        departments={"개발팀", "영업팀"},
        folders={"/company"},
    )


def test_valid_table_dept_viewer_grant_to_department():
    v = _table_validator()
    tup = v.validate({
        "action": "grant",
        "subject": "department:개발팀#member",
        "relation": "dept_viewer",
        "object": "table:employees",
    })
    assert tup == ("department:개발팀#member", "dept_viewer", "table:employees", "grant")


def test_valid_table_dept_viewer_grant_to_user():
    v = _table_validator()
    tup = v.validate({
        "action": "grant",
        "subject": "user:user-jisoo",
        "relation": "dept_viewer",
        "object": "table:sales",
    })
    assert tup == ("user:user-jisoo", "dept_viewer", "table:sales", "grant")


def test_valid_table_dept_viewer_revoke():
    v = _table_validator()
    tup = v.validate({
        "action": "revoke",
        "subject": "department:영업팀#member",
        "relation": "dept_viewer",
        "object": "table:sales",
    })
    assert tup == ("department:영업팀#member", "dept_viewer", "table:sales", "revoke")


def test_reject_table_dept_viewer_unknown_table():
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "department:개발팀#member",
        "relation": "dept_viewer",
        "object": "table:secret_data",
    }) is None


def test_reject_table_dept_viewer_unknown_department():
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "department:마케팅팀#member",
        "relation": "dept_viewer",
        "object": "table:employees",
    }) is None


def test_reject_table_can_access_direct_grant():
    # can_access는 더 이상 grant 대상이 아님 — dept_viewer만 허용
    v = _table_validator()
    assert v.validate({
        "action": "grant",
        "subject": "user:user-jisoo",
        "relation": "can_access",
        "object": "table:employees",
    }) is None


def test_catalog_text_contains_table_names():
    v = _table_validator()
    text = v.catalog_text()
    assert "employees" in text
    assert "sales" in text
    assert "테이블" in text

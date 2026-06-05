from core.fga.permission_validator import PermissionValidator

# 화이트리스트를 직접 주입(config 파일 비의존 단위 테스트)
def _validator():
    return PermissionValidator(
        user_ids={"user-jisoo", "user-minjun"},
        departments={"개발", "영업"},
        permissions={"기본", "인사", "개발", "전사"},
    )


def test_valid_department_member_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-jisoo",
                      "relation": "member", "object": "department:개발"})
    assert tup == ("user:user-jisoo", "member", "department:개발", "grant")


def test_valid_holder_grant_to_user():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "grant")


def test_valid_holder_grant_to_department():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "department:개발#member",
                      "relation": "holder", "object": "permission:개발"})
    assert tup == ("department:개발#member", "holder", "permission:개발", "grant")


def test_valid_holder_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "revoke")


def test_holder_informal_user_subject():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "minjun",
                      "relation": "holder", "object": "permission:인사"})
    assert tup == ("user:user-minjun", "holder", "permission:인사", "grant")


def test_reject_holder_unknown_permission():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-minjun",
                       "relation": "holder", "object": "permission:secret"}) is None


def test_reject_holder_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "holder", "object": "permission:인사"}) is None


def test_reject_dept_viewer_relation_gone():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "department:개발#member",
                       "relation": "dept_viewer", "object": "folder:/company/hr"}) is None


def test_catalog_text_contains_permissions():
    v = _validator()
    text = v.catalog_text()
    assert "인사" in text and ("permission" in text.lower() or "권한" in text)


def test_valid_revoke():
    v = _validator()
    tup = v.validate({"action": "revoke", "subject": "user:user-minjun",
                      "relation": "member", "object": "department:영업"})
    assert tup == ("user:user-minjun", "member", "department:영업", "revoke")


def test_reject_unknown_user():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-eve",
                       "relation": "member", "object": "department:개발"}) is None


def test_reject_unknown_department():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": "member", "object": "department:marketing"}) is None


def test_reject_type_mismatch_member_to_folder():
    # member relation인데 object가 folder → 타입 정합 위반
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": "member", "object": "folder:/company"}) is None


def test_reject_bad_action():
    v = _validator()
    assert v.validate({"action": "delete_all", "subject": "user:user-jisoo",
                       "relation": "member", "object": "department:개발"}) is None


def test_reject_whitespace_injection():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo x",
                       "relation": "member", "object": "department:개발"}) is None


def test_catalog_text_contains_known_ids():
    v = _validator()
    text = v.catalog_text()
    assert "user-jisoo" in text and "개발" in text


def test_reject_null_subject_no_crash():
    v = _validator()
    # LLM이 JSON null을 낸 경우 — 크래시 없이 None 반환(fail-closed)
    assert v.validate({"action": "grant", "subject": None,
                       "relation": "member", "object": "department:개발"}) is None


def test_reject_null_relation_no_crash():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-jisoo",
                       "relation": None, "object": "department:개발"}) is None


# --- _resolve_user: 결정론적 사용자 참조 정규화 (ADR-0029/0031 후속) ---

def _resolver_validator():
    # 비격식 이름·접미 모호성 검증용 작은 카탈로그
    return PermissionValidator(
        user_ids={"user-alice", "user-bob", "user-team-bob"},
        departments={"개발"},
        permissions={"기본"},
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
                      "relation": "member", "object": "department:개발"})
    assert tup == ("user:user-alice", "member", "department:개발", "grant")


def test_validate_member_grant_canonical_subject_still_passes():
    # 이미 정식 입력은 여전히 통과 (기존 동작 보존)
    v = _resolver_validator()
    tup = v.validate({"action": "grant", "subject": "user:user-bob",
                      "relation": "member", "object": "department:개발"})
    assert tup == ("user:user-bob", "member", "department:개발", "grant")


def test_validate_member_grant_ambiguous_subject_denied():
    # 모호한 subject "bob"은 여전히 None (RISK_DENY)
    v = _resolver_validator()
    assert v.validate({"action": "grant", "subject": "bob",
                       "relation": "member", "object": "department:개발"}) is None


def test_validate_member_grant_unknown_subject_denied():
    v = _resolver_validator()
    assert v.validate({"action": "grant", "subject": "eve",
                       "relation": "member", "object": "department:개발"}) is None

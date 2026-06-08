from core.fga.permission_validator import PermissionValidator

# 화이트리스트를 직접 주입(config 파일 비의존 단위 테스트)
def _validator():
    return PermissionValidator(
        user_ids={"user-joohwan", "user-minjun"},
        departments={"개발", "영업"},
        permissions={"기본", "인사", "개발", "전사"},
    )


def test_valid_department_member_grant():
    v = _validator()
    tup = v.validate({"action": "grant", "subject": "user:user-joohwan",
                      "relation": "member", "object": "department:개발"})
    assert tup == ("user:user-joohwan", "member", "department:개발", "grant")


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
    assert v.validate({"action": "grant", "subject": "user:user-joohwan",
                       "relation": "member", "object": "department:marketing"}) is None


def test_reject_type_mismatch_member_to_folder():
    # member relation인데 object가 folder → 타입 정합 위반
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-joohwan",
                       "relation": "member", "object": "folder:/company"}) is None


def test_reject_bad_action():
    v = _validator()
    assert v.validate({"action": "delete_all", "subject": "user:user-joohwan",
                       "relation": "member", "object": "department:개발"}) is None


def test_reject_whitespace_injection():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-joohwan x",
                       "relation": "member", "object": "department:개발"}) is None


def test_catalog_text_contains_known_ids():
    v = _validator()
    text = v.catalog_text()
    assert "user-joohwan" in text and "개발" in text


def test_reject_null_subject_no_crash():
    v = _validator()
    # LLM이 JSON null을 낸 경우 — 크래시 없이 None 반환(fail-closed)
    assert v.validate({"action": "grant", "subject": None,
                       "relation": "member", "object": "department:개발"}) is None


def test_reject_null_relation_no_crash():
    v = _validator()
    assert v.validate({"action": "grant", "subject": "user:user-joohwan",
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


# ── resolve_user_id / catalog (이름→id 정규화, 데모 ⑪⑬⑮ 버그 수정) ──
def _named_validator():
    return PermissionValidator(
        user_ids={"user-daesu", "user-mido", "user-joohwan", "user-admin"},
        departments={"개발", "제품"},
        permissions={"기본"},
        names={"오대수": "user-daesu", "미도": "user-mido",
               "노주환": "user-joohwan", "이우진": "user-admin"},
    )


def test_resolve_user_id_by_korean_name():
    # 이슈1: "오대수" → user-daesu (LLM의 user-odaesu 환각 방지)
    assert _named_validator().resolve_user_id("오대수") == "user-daesu"


def test_resolve_user_id_strips_user_prefix():
    # 이슈2: "user:user-mido" → user-mido (self 판별용 정규화)
    assert _named_validator().resolve_user_id("user:user-mido") == "user-mido"


def test_resolve_user_id_bare_and_informal():
    v = _named_validator()
    assert v.resolve_user_id("user-daesu") == "user-daesu"
    assert v.resolve_user_id("mido") == "user-mido"  # username → user-mido


def test_resolve_user_id_unknown_and_none():
    v = _named_validator()
    assert v.resolve_user_id("user-odaesu") is None  # 환각 id → None(전체조회 폴백)
    assert v.resolve_user_id("없는사람") is None
    assert v.resolve_user_id(None) is None
    assert v.resolve_user_id("") is None


def test_is_known_user_id():
    v = _named_validator()
    assert v.is_known_user_id("user-daesu") is True
    assert v.is_known_user_id("user-odaesu") is False


def test_user_catalog_text_pairs_id_and_name():
    text = _named_validator().user_catalog_text()
    assert "user-daesu(오대수)" in text
    assert "user-mido(미도)" in text


def test_validator_without_names_still_resolves_ids():
    # names 미지정(기본값) — 기존 호출부 보존, id 형태는 여전히 해석
    v = PermissionValidator(user_ids={"user-joohwan"}, departments=set(), permissions=set())
    assert v.resolve_user_id("user:user-joohwan") == "user-joohwan"
    assert v.resolve_user_id("오대수") is None

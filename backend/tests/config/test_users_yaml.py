from pathlib import Path

import yaml

from scripts.seed_business import build_employee_rows
from scripts.seed_fga import _build_tuples

_USERS_YAML = Path(__file__).resolve().parents[2] / "config" / "users.yaml"
_REAL_DEPTS = {"개발", "제품", "영업", "인사", "재무", "법무", "디자인"}


def _load():
    return yaml.safe_load(_USERS_YAML.read_text())["users"]


def test_users_yaml_has_thirty_accounts():
    assert len(_load()) == 30


def test_employee_rows_total_thirty():
    rows = build_employee_rows(_load())
    assert len(rows) == 30


def test_usernames_and_user_ids_unique():
    users = _load()
    usernames = [u["username"] for u in users]
    user_ids = [u["user_id"] for u in users]
    assert len(set(usernames)) == 30
    assert len(set(user_ids)) == 30


def test_exactly_one_team_lead_per_real_department():
    users = _load()
    leads_by_dept: dict[str, list[str]] = {}
    for u in users:
        for dept in u.get("dept_admin_of", []) or []:
            leads_by_dept.setdefault(dept, []).append(u["username"])
    # 7개 실부서 각각 정확히 1명의 팀장
    assert set(leads_by_dept) == _REAL_DEPTS
    for dept, leads in leads_by_dept.items():
        assert len(leads) == 1, f"{dept} 팀장이 {leads}로 1명이 아님"


def test_each_team_lead_is_member_of_its_department():
    # dept_admin_of 부서는 본인 departments에 포함되어야 한다(고아 위임 방지)
    for u in _load():
        for dept in u.get("dept_admin_of", []) or []:
            assert dept in (u.get("departments") or []), f"{u['username']} 위임 부서 모순"


def test_fga_emits_seven_dept_admin_tuples():
    tuples = _build_tuples(_load(), {}, {})
    admin_tuples = [
        t for t in tuples
        if t["relation"] == "admin" and t["object"].startswith("department:")
    ]
    assert len(admin_tuples) == 7

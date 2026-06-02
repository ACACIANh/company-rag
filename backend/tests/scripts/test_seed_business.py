from scripts.seed_business import (
    build_employee_rows,
    build_sales_rows,
    _grant_sql,
    _primary_department,
)

_USERS = [
    {"username": "admin", "user_id": "user-admin", "fga_roles": ["c_level"]},
    {"username": "alice", "user_id": "user-alice", "departments": ["engineering"]},
    {"username": "carol", "user_id": "user-carol", "departments": []},
    {"username": "ivan", "user_id": "user-ivan", "departments": ["engineering", "product"]},
]


# ── _primary_department ─────────────────────────────────────
def test_primary_department_first_of_list():
    assert _primary_department({"departments": ["engineering", "product"]}) == "engineering"


def test_primary_department_c_level_is_executive():
    assert _primary_department({"fga_roles": ["c_level"]}) == "executive"


def test_primary_department_unassigned():
    assert _primary_department({"departments": []}) == "unassigned"


# ── build_employee_rows ─────────────────────────────────────
def test_employee_rows_count_matches_users():
    rows = build_employee_rows(_USERS)
    assert len(rows) == len(_USERS)


def test_employee_row_has_pii_columns():
    # (emp_id, name, department, position, hire_date, salary, email)
    rows = build_employee_rows(_USERS)
    admin = rows[0]
    assert admin[0] == "user-admin"
    assert admin[3] == "CTO"
    assert isinstance(admin[5], int) and admin[5] > 0   # salary (PII)
    assert admin[6] == "admin@techcorp.example"          # email (PII)


def test_employee_rows_deterministic():
    assert build_employee_rows(_USERS) == build_employee_rows(_USERS)


def test_employee_cross_department_uses_first():
    rows = build_employee_rows(_USERS)
    ivan = next(r for r in rows if r[0] == "user-ivan")
    assert ivan[2] == "engineering"


# ── build_sales_rows ────────────────────────────────────────
def test_sales_rows_deterministic_and_nonempty():
    rows = build_sales_rows()
    assert rows == build_sales_rows()
    assert len(rows) == 5 * 4   # 5 periods × 4 depts


def test_sales_row_shape():
    # (period, department, product, amount)
    row = build_sales_rows()[0]
    assert len(row) == 4
    assert row[0] == "2025-Q1"          # period
    assert isinstance(row[3], int) and row[3] > 0   # amount


# ── _grant_sql 격리 ─────────────────────────────────────────
def test_grant_sql_revokes_public_and_grants_business_readonly():
    sql = _grant_sql("pw")
    assert "REVOKE ALL ON SCHEMA public FROM sql_tool_ro" in sql
    assert "GRANT USAGE ON SCHEMA business TO sql_tool_ro" in sql
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA business TO sql_tool_ro" in sql
    # 쓰기 권한은 부여하지 않는다
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT ALL" not in sql


def test_grant_sql_account_level_hardening():
    sql = _grant_sql("pw")
    assert "default_transaction_read_only = on" in sql
    assert "statement_timeout" in sql


def test_grant_sql_escapes_single_quote():
    sql = _grant_sql("a'b")
    assert "a''b" in sql

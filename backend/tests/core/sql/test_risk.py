from core.sql.risk import (
    classify_sql_ast,
    RISK_SELECT,
    RISK_UPDATE_DELETE,
    RISK_DDL,
    RISK_DENY,
)


# ── 일반 읽기 ───────────────────────────────────────────────
def test_plain_select():
    assert classify_sql_ast("SELECT * FROM business.employees") == RISK_SELECT


def test_select_with_subquery():
    sql = "SELECT id FROM business.sales WHERE department IN (SELECT department FROM business.employees)"
    assert classify_sql_ast(sql) == RISK_SELECT


def test_select_with_cte():
    sql = "WITH c AS (SELECT 1 AS x) SELECT x FROM c"
    assert classify_sql_ast(sql) == RISK_SELECT


# ── 쓰기 ────────────────────────────────────────────────────
def test_update():
    assert classify_sql_ast("UPDATE business.employees SET salary = 0 WHERE emp_id = 'x'") == RISK_UPDATE_DELETE


def test_delete():
    assert classify_sql_ast("DELETE FROM business.employees WHERE emp_id = 'x'") == RISK_UPDATE_DELETE


def test_insert_is_write():
    assert classify_sql_ast("INSERT INTO business.sales (period) VALUES ('2026-Q2')") == RISK_DENY


# ── 우회 차단: SELECT로 위장한 data-modifying CTE ────────────
def test_data_modifying_cte_in_select_is_write():
    # WHERE 없는 DELETE → DENY (WHERE 가드 적용, 우회 차단도 유지)
    sql = "WITH x AS (DELETE FROM business.employees RETURNING *) SELECT * FROM x"
    assert classify_sql_ast(sql) == RISK_DENY


# ── DDL ─────────────────────────────────────────────────────
def test_drop_is_ddl():
    assert classify_sql_ast("DROP TABLE business.employees") == RISK_DDL


def test_alter_is_ddl():
    assert classify_sql_ast("ALTER TABLE business.employees ADD COLUMN c int") == RISK_DDL


def test_truncate_is_ddl():
    assert classify_sql_ast("TRUNCATE business.employees") == RISK_DDL


# ── 승급: 가장 위험한 등급으로 ───────────────────────────────
def test_multi_statement_promotes_to_worst():
    assert classify_sql_ast("SELECT 1; DROP TABLE business.employees") == RISK_DDL


# ── 보수적 폴백 → DENY ──────────────────────────────────────
def test_empty_is_deny():
    assert classify_sql_ast("") == RISK_DENY
    assert classify_sql_ast("   ") == RISK_DENY


def test_unparseable_is_deny():
    assert classify_sql_ast("}{ not valid sql ][") == RISK_DENY


def test_unsupported_command_is_deny():
    # sqlglot이 구조화하지 못하는 raw 구문(Command)은 미지원 → DENY
    assert classify_sql_ast("VACUUM business.employees") == RISK_DENY


# ── WHERE 가드 + INSERT/MERGE 차단 ──────────────────────────────
def test_update_with_where_is_update_delete():
    assert classify_sql_ast("UPDATE business.employees SET salary = 1 WHERE emp_id = 'x'") == RISK_UPDATE_DELETE

def test_delete_with_where_is_update_delete():
    assert classify_sql_ast("DELETE FROM business.employees WHERE emp_id = 'x'") == RISK_UPDATE_DELETE

def test_update_without_where_is_deny():
    assert classify_sql_ast("UPDATE business.employees SET salary = 0") == RISK_DENY

def test_delete_without_where_is_deny():
    assert classify_sql_ast("DELETE FROM business.employees") == RISK_DENY

def test_insert_is_deny():
    assert classify_sql_ast("INSERT INTO business.employees (emp_id) VALUES ('x')") == RISK_DENY

def test_plain_select_unaffected():
    assert classify_sql_ast("SELECT salary FROM business.employees WHERE emp_id = 'x'") == RISK_SELECT

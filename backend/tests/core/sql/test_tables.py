from core.sql.tables import extract_tables


def test_simple_select():
    assert extract_tables("SELECT * FROM business.employees") == {"employees"}


def test_join_two_tables():
    sql = "SELECT e.name FROM business.employees e JOIN business.sales s ON e.department = s.department"
    assert extract_tables(sql) == {"employees", "sales"}


def test_bare_table_name():
    assert extract_tables("SELECT * FROM employees WHERE emp_id = 1") == {"employees"}


def test_update_delete_tables():
    assert extract_tables("UPDATE business.employees SET salary = 0 WHERE emp_id = 1") == {"employees"}
    assert extract_tables("DELETE FROM business.sales WHERE sale_id = 2") == {"sales"}


def test_cte_alias_excluded():
    sql = (
        "WITH top AS (SELECT department FROM business.sales) "
        "SELECT * FROM top JOIN business.employees ON top.department = employees.department"
    )
    # CTE 이름 'top'은 base 테이블이 아니므로 제외, 실제 테이블만.
    assert extract_tables(sql) == {"sales", "employees"}


def test_no_table_select_constant():
    assert extract_tables("SELECT 1") == set()


def test_parse_failure_returns_empty():
    assert extract_tables("") == set()
    assert extract_tables("NOT SQL AT ALL ;;;") == set()

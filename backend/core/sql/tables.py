"""SQL 참조 테이블 추출 (ADR-0047) — 순수 로직, LangGraph 무관.

생성된 SQL이 건드리는 base 테이블의 bare 이름을 sqlglot AST로 모은다.
테이블별 접근 게이트(core.sql.gate.gate_table_access)가 이 목록으로 신원별
`table:<name>` can_access를 교차한다. CTE 별칭은 base 테이블이 아니므로 제외하고,
파싱 실패·빈 입력은 빈 집합으로 닫는다(호출자가 보수적으로 처리).
"""
import sqlglot
from sqlglot import exp


def extract_tables(sql: str) -> set[str]:
    """SQL이 참조하는 base 테이블 bare 이름 집합. CTE 별칭은 제외.

    스키마 한정자(business.)는 떼고 테이블명만 반환한다(table:employees 매칭용).
    파싱 실패·빈 입력은 빈 집합 — 참조 테이블 없음으로 본다.
    """
    if not sql or not sql.strip():
        return set()
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except Exception:
        return set()
    tables: set[str] = set()
    cte_names: set[str] = set()
    for stmt in statements:
        if stmt is None:
            continue
        for cte in stmt.find_all(exp.CTE):
            cte_names.add(cte.alias_or_name)
        for table in stmt.find_all(exp.Table):
            tables.add(table.name)
    return {t for t in tables if t and t not in cte_names}

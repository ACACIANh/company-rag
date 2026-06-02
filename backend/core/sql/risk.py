"""SQL 위험도 분류 — AST 확정 (ADR-0017).

sqlglot AST로 구문 종류를 결정론적으로 확정한다. 서브쿼리·CTE를 포함한
전체 트리를 검사해 하나라도 쓰기/DDL이 섞이면 그 등급으로 승급한다.
파싱 실패·빈 입력·미지원(raw) 구문은 보수적으로 DENY로 닫는다.

"대량/PII" 의미 판단(RISK_BULK_SELECT 승급)은 여기서 하지 않는다 — LLM 보강
단계(분류 노드)의 책임이다. 본 모듈은 LangGraph를 모르는 순수 로직이다.
"""
import sqlglot
from sqlglot import exp

RISK_SELECT = "select"
RISK_BULK_SELECT = "bulk_select"   # 대량·PII — LLM 보강에서만 승급
RISK_UPDATE_DELETE = "update_delete"
RISK_DDL = "ddl"
RISK_DENY = "deny"                  # 보수적 폴백(파싱 실패·미지원·모호)

# 위험도 순위 (승급 비교용). 높을수록 위험.
RISK_RANK = {
    RISK_SELECT: 1,
    RISK_BULK_SELECT: 2,
    RISK_UPDATE_DELETE: 3,
    RISK_DDL: 4,
    RISK_DENY: 5,
}

_DDL_TYPES = (exp.Create, exp.Drop, exp.Alter, exp.TruncateTable)
_WRITE_TYPES = (exp.Insert, exp.Update, exp.Delete, exp.Merge)


def _classify_statement(stmt: exp.Expression) -> str:
    # sqlglot이 구조화하지 못한 raw 구문(Command, 예: VACUUM)은 미지원 → DENY
    if isinstance(stmt, exp.Command) or list(stmt.find_all(exp.Command)):
        return RISK_DENY
    # DDL > 쓰기 > 읽기 순으로 가장 위험한 등급 확정 (CTE 내 data-modifying 포함)
    if list(stmt.find_all(*_DDL_TYPES)):
        return RISK_DDL
    if list(stmt.find_all(*_WRITE_TYPES)):
        return RISK_UPDATE_DELETE
    if isinstance(stmt, exp.Select) or list(stmt.find_all(exp.Select)):
        return RISK_SELECT
    return RISK_DENY


def classify_sql_ast(sql: str) -> str:
    """SQL 문자열을 AST로 파싱해 위험도 등급을 결정론적으로 확정한다.

    반환: RISK_SELECT / RISK_UPDATE_DELETE / RISK_DDL / RISK_DENY.
    (RISK_BULK_SELECT는 본 함수가 반환하지 않는다 — LLM 보강 전용.)
    여러 statement면 가장 위험한 등급으로 승급한다.
    """
    if not sql or not sql.strip():
        return RISK_DENY
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except Exception:
        return RISK_DENY
    statements = [s for s in statements if s is not None]
    if not statements:
        return RISK_DENY

    worst = RISK_SELECT
    for stmt in statements:
        level = _classify_statement(stmt)
        if RISK_RANK[level] > RISK_RANK[worst]:
            worst = level
    return worst

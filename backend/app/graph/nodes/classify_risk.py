"""SQL 위험도 분류 노드 (ADR-0017).

AST로 구문 종류를 결정론적으로 확정하고(core.sql.risk), 순수 SELECT로
확정된 경우에만 LLM으로 대량/PII 여부를 보강한다. LLM은 등급을 낮추지
못한다 — SELECT → 대량 SELECT 승급(상향)만 가능하다.
"""
from core.llm.base import LLMClient
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, classify_sql_ast
from app.graph.prompts import SQL_BULK_PII_PROMPT


def classify_risk_node(state: dict, *, llm: LLMClient) -> dict:
    sql = state["generated_sql"]
    risk = classify_sql_ast(sql)

    # AST가 순수 SELECT로 확정한 경우에만 LLM이 대량/PII 보강(상향만).
    # 쓰기·DDL·DENY는 확정 사실이므로 LLM을 거치지 않는다.
    if risk == RISK_SELECT:
        response = llm.complete(SQL_BULK_PII_PROMPT.format(sql=sql)).strip().lower()
        if response.startswith("yes"):
            risk = RISK_BULK_SELECT

    return {"sql_risk": risk}

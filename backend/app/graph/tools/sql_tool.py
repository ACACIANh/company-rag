"""SQL 조회 도구 핸들러 (ADR-0023). NL 질문 → SQL → 위험도 → (게이트) → 실행.

NL→SQL·위험도 분류·결과 포매팅은 기존 노드 로직(ADR-0016/0017/0021)을 재사용한다.
실행은 read-only 제한계정 풀(ADR-0020)에서만 한다.
"""
import asyncpg
from langchain_core.tools import Tool

from core.llm.base import LLMClient
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, classify_sql_ast
from app.graph.prompts import SQL_GENERATE_PROMPT, SQL_BULK_PII_PROMPT
from app.graph.nodes.sql_generate import _strip_code_fence

_DEFAULT_ROW_LIMIT = 100

_DESCRIPTION = (
    "사내 업무 DB(business.employees, business.sales)의 레코드·집계 값을 조회한다. "
    "정책·규정 같은 문서 내용이 아니라 '테이블 값으로 답하는' 질문에만 쓴다. "
    "question 인자에 한국어 자연어 질문을 그대로 넣는다."
)


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join(str(r[c]) for c in cols))
    return "\n".join(lines)


class SqlToolHandler:
    name = "query_business_data"

    def __init__(self, *, llm: LLMClient, sql_pool: asyncpg.Pool, row_limit: int = _DEFAULT_ROW_LIMIT) -> None:
        self._llm = llm
        self._pool = sql_pool
        self._row_limit = row_limit
        self.tool = Tool(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda question: "",
        )

    def plan(self, args: dict) -> tuple[str, str]:
        question = args["question"]
        raw = self._llm.complete(SQL_GENERATE_PROMPT.format(question=question))
        sql = _strip_code_fence(raw)
        risk = classify_sql_ast(sql)
        if risk == RISK_SELECT:
            response = self._llm.complete(SQL_BULK_PII_PROMPT.format(sql=sql)).strip().lower()
            if response.startswith("yes"):
                risk = RISK_BULK_SELECT
        return sql, risk

    async def aexecute(self, planned_action: str) -> str:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(planned_action)
            return _format_rows(list(rows)[:self._row_limit])
        except Exception as exc:
            return f"SQL 실행 오류: {type(exc).__name__}"

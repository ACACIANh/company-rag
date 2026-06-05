"""SQL 조회 도구 에이전트 (ADR-0023). NL 질문 → SQL → 위험도 → (게이트) → 실행.

NL→SQL·위험도 분류·결과 포매팅은 기존 노드 로직(ADR-0016/0017/0021)을 재사용한다.
실행은 read-only 제한계정 풀(SELECT)과 쓰기 제한계정 풀(UPDATE/DELETE)로 분리한다(ADR-0020/0034).
"""
import asyncpg
from langchain_core.tools import Tool

from core.llm.base import LLMClient
from core.sql.risk import RISK_SELECT, RISK_BULK_SELECT, RISK_UPDATE_DELETE, classify_sql_ast
from app.graph.prompts import SQL_GENERATE_PROMPT, SQL_BULK_PII_PROMPT
from app.graph.tools._utils import strip_code_fence
from app.graph.tools._args import single_text_arg
from app.graph.tools.base import ToolResult

_DEFAULT_ROW_LIMIT = 100

_DESCRIPTION = (
    "사내 업무 DB(business.employees, business.sales, business.equipment)의 레코드를 조회·수정·삭제한다. "
    "직원의 사번·아이디(emp_id)·부서·직급·이메일·연봉, 매출 수치, 장비(자산) 현황 등 테이블 값을 묻는 조회뿐 아니라 "
    "'연봉을 바꿔줘', '장비를 지급해줘', '행을 삭제해줘' 같은 데이터 변경도 이 도구로 처리한다. "
    "특정 직원의 아이디/사번을 이름으로 찾는 것도 여기서 한다(감사 이력·권한 조회 도구가 아니다). "
    "권한 부여/회수가 아니라 '테이블 데이터' 작업일 때 쓴다. "
    "question 인자에 한국어 자연어 요청을 그대로 넣는다."
)


def _affected_rows(status: str) -> str:
    """asyncpg execute status('UPDATE 3'/'DELETE 2')에서 영향 행 수 추출."""
    parts = status.split()
    return parts[-1] if parts and parts[-1].isdigit() else "0"


def _format_rows(rows: list) -> str:
    if not rows:
        return "(결과 없음)"
    cols = list(rows[0].keys())
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    data_lines = ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join([header, separator, *data_lines])


class SqlAgent:
    name = "query_business_data"
    label = "sql"

    def __init__(self, *, llm: LLMClient, sql_pool: asyncpg.Pool | None, sql_rw_pool: asyncpg.Pool | None = None, row_limit: int = _DEFAULT_ROW_LIMIT) -> None:
        self._llm = llm
        self._pool = sql_pool
        self._rw_pool = sql_rw_pool
        self._row_limit = row_limit
        self.tool = Tool(
            name=self.name,
            description=_DESCRIPTION,
            func=lambda question: "",
        )

    def plan(self, args: dict) -> tuple[str, str]:
        question = single_text_arg(args, prefer="question")
        raw = self._llm.complete(SQL_GENERATE_PROMPT.format(question=question))
        sql = strip_code_fence(raw)
        risk = classify_sql_ast(sql)
        if risk == RISK_SELECT:
            response = self._llm.complete(SQL_BULK_PII_PROMPT.format(sql=sql)).strip().lower()
            if response.startswith("yes"):
                risk = RISK_BULK_SELECT
        return sql, risk

    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        if risk == RISK_UPDATE_DELETE:
            if self._rw_pool is None:
                msg = "SQL 실행 오류: 쓰기 풀 미구성"
                return ToolResult(text=msg, summary=msg)
            try:
                async with self._rw_pool.acquire() as conn:
                    async with conn.transaction():
                        status = await conn.execute(planned_action)
                n = _affected_rows(status)
                return ToolResult(text=f"{n}개 행이 변경되었습니다.", summary=f"{n}행 변경")
            except Exception as exc:
                msg = f"SQL 실행 오류: {type(exc).__name__}"
                return ToolResult(text=msg, summary=msg)
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(planned_action)
            limited = list(rows)[:self._row_limit]
            return ToolResult(text=_format_rows(limited), summary=f"{len(limited)}행 조회")
        except Exception as exc:
            msg = f"SQL 실행 오류: {type(exc).__name__}"
            return ToolResult(text=msg, summary=msg)

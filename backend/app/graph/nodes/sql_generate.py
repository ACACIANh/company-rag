"""자연어 → SQL 생성 노드 (ADR-0016 게이트 입력 생성).

business 스키마(가상 업무 DB)만 대상으로 LLM이 SQL을 생성한다. 생성된 SQL은
위험도 분류(ADR-0017)·게이트(ADR-0016)를 거쳐서만 실행된다 — 여기서 검증/실행은 하지 않는다.
"""
from core.llm.base import LLMClient
from app.graph.prompts import SQL_GENERATE_PROMPT


def _strip_code_fence(text: str) -> str:
    """LLM이 감싼 ```sql ... ``` / ``` ... ``` 코드펜스를 제거한다."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        # 첫 줄(``` 또는 ```sql)과 마지막 ``` 줄 제거
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def sql_generate_node(state: dict, *, llm: LLMClient) -> dict:
    question = state.get("rewritten_question") or state["question"]
    raw = llm.complete(SQL_GENERATE_PROMPT.format(question=question))
    return {"generated_sql": _strip_code_fence(raw)}

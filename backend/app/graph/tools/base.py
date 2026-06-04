"""도구 핸들러 추상화 (ADR-0023) — app 계층(LangChain 인지).

도구 = LLM에 노출할 LangChain Tool 정의 + 서버측 핸들러(plan/execute).
plan은 인자를 '구체화된 동작 + 위험도'로 바꾼다(SQL이면 생성된 SQL + 위험도 등급).
execute는 그 동작을 실행해 결과 텍스트를 만든다. 게이트는 plan과 execute 사이에서 돈다.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolHandler(Protocol):
    name: str

    def plan(self, args: dict) -> tuple[str, str]:
        """도구 인자 → (구체화된 동작, core.sql.risk 위험도 등급)."""
        ...

    async def execute(self, planned_action: str, risk: str) -> str:
        """구체화된 동작 실행 → 결과 텍스트. risk는 실행 경로(읽기/쓰기) 선택에 쓴다."""
        ...

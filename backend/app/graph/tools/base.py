"""도구 에이전트 추상화 (ADR-0023) — app 계층(LangChain 인지).

도구 = LLM에 노출할 LangChain Tool 정의 + 서버측 에이전트(plan/execute).
plan은 인자를 '구체화된 동작 + 위험도'로 바꾼다(SQL이면 생성된 SQL + 위험도 등급).
execute는 그 동작을 실행해 결과를 만든다. 게이트는 plan과 execute 사이에서 돈다.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolResult:
    """도구 실행 결과. text=사용자 노출 전체 텍스트, summary=감사로그용 짧은 한 줄 (ADR-0052)."""

    text: str
    summary: str


@runtime_checkable
class ToolAgent(Protocol):
    name: str
    label: str

    def plan(self, args: dict) -> tuple[str, str]:
        """도구 인자 → (구체화된 동작, core.sql.risk 위험도 등급)."""
        ...

    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        """구체화된 동작 실행 → ToolResult. risk는 실행 경로(읽기/쓰기) 선택에 쓴다."""
        ...

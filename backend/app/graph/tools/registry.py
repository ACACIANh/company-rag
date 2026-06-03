"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import Tool

from core.llm.base import LLMClient
from app.graph.tools.sql_tool import SqlToolHandler


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolHandler
    tool_defs: list[Tool]   # bind_tools용


def build_tool_registry(*, llm: LLMClient, sql_pool) -> ToolRegistry:
    sql = SqlToolHandler(llm=llm, sql_pool=sql_pool)
    handlers = {sql.name: sql}
    tool_defs = [sql.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)

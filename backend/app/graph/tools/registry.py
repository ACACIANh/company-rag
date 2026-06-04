"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from app.graph.tools.audit_history_tool import AuditHistoryToolHandler
from app.graph.tools.sql_tool import SqlAgent
from app.graph.tools.permission_tool import PermissionToolHandler


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolHandler
    tool_defs: list[BaseTool]   # bind_tools용


def build_tool_registry(
    *, llm: LLMClient, sql_pool, sql_rw_pool=None, fga_client: FGAClient, app_pool=None
) -> ToolRegistry:
    sql = SqlAgent(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool)
    permission = PermissionToolHandler(
        llm=llm, fga_client=fga_client, validator=PermissionValidator.from_config()
    )
    audit = AuditHistoryToolHandler(fga_client=fga_client, app_pool=app_pool)
    handlers = {sql.name: sql, permission.name: permission, audit.name: audit}
    tool_defs = [sql.tool, permission.tool, audit.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)

"""도구 레지스트리 (ADR-0023). 도구명 → 핸들러, bind_tools용 Tool 정의 목록.

새 도구 추가 = 여기에 핸들러를 한 줄 등록(+위험도 분류기). (사용자 동기: 권한 도구 추가 용이)
"""
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from app.graph.tools.audit_history_tool import AuditAgent
from app.graph.tools.sql_tool import SqlAgent
from app.graph.tools.permission_tool import PermissionAgent


@dataclass
class ToolRegistry:
    handlers: dict          # name -> ToolAgent
    tool_defs: list[BaseTool]   # bind_tools용


def build_tool_registry(
    *, llm: LLMClient, sql_pool, sql_rw_pool=None, fga_client: FGAClient, app_pool=None
) -> ToolRegistry:
    sql = SqlAgent(llm=llm, sql_pool=sql_pool, sql_rw_pool=sql_rw_pool)
    validator = PermissionValidator.from_config()
    permission = PermissionAgent(llm=llm, fga_client=fga_client, validator=validator)
    audit = AuditAgent(fga_client=fga_client, app_pool=app_pool, validator=validator)
    handlers = {sql.name: sql, permission.name: permission, audit.name: audit}
    tool_defs = [sql.tool, permission.tool, audit.tool]
    return ToolRegistry(handlers=handlers, tool_defs=tool_defs)


# 도구 라벨 SSOT: 등록된 도구 클래스에서 name→label 자동 수집 (ADR 후속).
# 새 도구 추가 = _TOOL_CLASSES에 한 줄 + 클래스에 label 선언. 수동 매핑 테이블 없음.
_TOOL_CLASSES = (SqlAgent, PermissionAgent, AuditAgent)


def tool_label_map() -> dict[str, str]:
    """도구명(name) → 역할 라벨(label) 맵. 응답 조립부가 사용 도구를 라벨로 변환할 때 사용."""
    return {cls.name: cls.label for cls in _TOOL_CLASSES}

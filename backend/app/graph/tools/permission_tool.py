"""권한 관리 도구 에이전트 (ADR-0029). NL 지시 → 구조화 파싱 → 화이트리스트 검증 →
(게이트) → FGA 튜플 쓰기. SQL 도구(query_business_data)와 동형.

plan은 LLM이 파싱한 {action,subject,relation,object}를 검증한다. 검증 실패는
RISK_DENY로 닫고, 통과는 RISK_GRANT(capability:admin 게이트 대상)로 낸다.
execute는 검증을 거친 planned_action만 받으므로 재검증 없이 튜플을 쓴다.
"""
import json

from langchain_core.tools import Tool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from core.sql.gate import RISK_GRANT
from core.sql.risk import RISK_DENY
from app.graph.prompts import PERMISSION_PARSE_PROMPT
from app.graph.tools._utils import strip_code_fence
from app.graph.tools._args import single_text_arg

_DESCRIPTION = (
    "사내 접근 권한을 부여/회수한다(데이터 값 변경이 아님): 부서 멤버십, 폴더 부서 접근권, SQL 실행 권한 등급. "
    "예: '앨리스를 엔지니어링 부서에 추가', '세일즈 부서의 재무 폴더 열람권 회수'. "
    "직원 연봉·매출 같은 테이블 데이터 수정은 이 도구가 아니라 query_business_data를 쓴다. "
    "instruction 인자에 한국어 자연어 지시를 그대로 넣는다."
)


class PermissionAgent:
    name = "manage_permission"

    def __init__(self, *, llm: LLMClient, fga_client: FGAClient, validator: PermissionValidator) -> None:
        self._llm = llm
        self._fga = fga_client
        self._validator = validator
        self.tool = Tool(name=self.name, description=_DESCRIPTION, func=lambda instruction: "")

    def plan(self, args: dict) -> tuple[str, str]:
        instruction = single_text_arg(args, prefer="instruction")
        prompt = (
            PERMISSION_PARSE_PROMPT
            .replace("{known_ids}", self._validator.catalog_text())
            .replace("{instruction}", instruction)
        )
        raw = self._llm.complete(prompt)
        try:
            parsed = json.loads(strip_code_fence(raw))
        except Exception:
            return "권한 동작 파싱 실패", RISK_DENY
        if not isinstance(parsed, dict):
            return "권한 동작 파싱 실패", RISK_DENY
        validated = self._validator.validate(parsed)
        if validated is None:
            return "검증 실패: 유효하지 않은 권한 동작", RISK_DENY
        subject, relation, object_, action = validated
        return f"{action} {subject} {relation} {object_}", RISK_GRANT

    async def execute(self, planned_action: str, risk: str) -> str:
        parts = planned_action.split(" ")
        if len(parts) != 4:
            return "권한 실행 오류: 잘못된 동작 형식"
        action, subject, relation, object_ = parts
        try:
            if action == "grant":
                await self._fga.grant_tuple(subject, relation, object_)
            elif action == "revoke":
                await self._fga.revoke_tuple(subject, relation, object_)
            else:
                return "권한 실행 오류: 알 수 없는 action"
            return f"완료: {planned_action}"
        except Exception as exc:
            return f"권한 실행 오류: {type(exc).__name__}"

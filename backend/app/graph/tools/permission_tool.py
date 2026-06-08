"""권한 관리 도구 에이전트 (ADR-0029). NL 지시 → 구조화 파싱 → 화이트리스트 검증 →
(게이트) → FGA 튜플 쓰기. SQL 도구(query_business_data)와 동형.

plan은 LLM이 파싱한 {action,subject,relation,object}를 검증한다. 검증 실패는
RISK_DENY로 닫고, 통과는 RISK_GRANT(capability:admin 게이트 대상)로 낸다.
execute는 검증을 거친 planned_action만 받으므로 재검증 없이 튜플을 쓴다.
"""
import asyncio
import json

from langchain_core.tools import Tool

from core.fga.client import FGAClient
from core.fga.permission_validator import PermissionValidator
from core.llm.base import LLMClient
from core.sql.gate import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_JUSTIFY_AND_APPROVE,
    RISK_GRANT,
    gate_decision,
)
from core.sql.risk import (
    RISK_BULK_SELECT,
    RISK_DDL,
    RISK_DENY,
    RISK_SELECT,
    RISK_UPDATE_DELETE,
)
from app.graph.prompts import PERMISSION_PARSE_PROMPT
from app.graph.tools.base import ToolResult
from app.graph.tools._utils import strip_code_fence
from app.graph.tools._args import single_text_arg

_DESCRIPTION = (
    "사내 접근 권한을 조회·부여·회수한다: 부서 멤버십, 폴더 접근권, SQL 실행 권한 등급. "
    "예: '내 접근 가능한 폴더 알려줘', 'alice 권한 조회', '앨리스를 엔지니어링 부서에 추가'. "
    "직원 연봉·매출 같은 테이블 데이터 수정은 이 도구가 아니라 query_business_data를 쓴다. "
    "instruction 인자에 한국어 자연어 지시를 그대로 넣는다."
)


class PermissionAgent:
    name = "manage_permission"
    label = "permission"

    def __init__(self, *, llm: LLMClient, fga_client: FGAClient, validator: PermissionValidator) -> None:
        self._llm = llm
        self._fga = fga_client
        self._validator = validator
        self.tool = Tool(name=self.name, description=_DESCRIPTION, func=lambda instruction: "")

    def plan(self, args: dict) -> tuple[str, str]:
        instruction = single_text_arg(args, prefer="instruction")
        caller = args.get("__caller_id", "")
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

        action = parsed.get("action")
        if action == "query":
            # LLM이 만든 target은 접두(user:)·로마자가 들쭉날쭉 → 서버측 정규화.
            # self 조회("내 권한")가 접두 불일치로 타인 조회로 오판되던 버그 수정(데모 ⑬⑮).
            raw_target = parsed.get("target_user_id")
            resolved = self._validator.resolve_user_id(raw_target) if raw_target else None
            target = resolved or caller
            return f"query {caller} {target}", RISK_SELECT

        validated = self._validator.validate(parsed)
        if validated is None:
            return "검증 실패: 유효하지 않은 권한 동작", RISK_DENY
        subject, relation, object_, action = validated
        return f"{action} {subject} {relation} {object_}", RISK_GRANT

    async def execute(self, planned_action: str, risk: str) -> ToolResult:
        if planned_action.startswith("query "):
            parts = planned_action.split(" ", 2)
            if len(parts) != 3:
                msg = "권한 조회 오류: 잘못된 동작 형식"
                return ToolResult(text=msg, summary=msg)
            _, caller, target = parts
            if target != caller:
                try:
                    admin_ok = await self._fga.check(f"user:{caller}", "justify_grant", "capability:admin")
                except Exception:
                    return ToolResult(text="권한 없음: 관리자 확인 실패", summary="권한 없음")
                if not admin_ok:
                    return ToolResult(text="권한 없음: 타인 조회는 관리자만 가능합니다.", summary="권한 없음")
            try:
                # 5개 조회는 모두 target 권한 읽기로 서로 독립 → gather로 병렬화
                # (직렬 ~15 FGA round-trip을 wall-clock 1~2회로 축약). 값·예외 처리 불변.
                departments, roles, folders, capabilities, tables = await asyncio.gather(
                    self._fga.user_departments(target),
                    self._fga.user_roles(target),
                    self._fga.get_readable_folders(target),
                    _resolve_capabilities(self._fga.check, target),
                    self._fga.user_accessible_tables(target),
                )
            except Exception as exc:
                msg = f"권한 조회 오류: {type(exc).__name__}"
                return ToolResult(text=msg, summary=msg)
            return ToolResult(
                text=_format_permission_snapshot(target, departments, roles, folders, capabilities, tables),
                summary=f"권한 스냅샷 조회({target})",
            )

        parts = planned_action.split(" ")
        if len(parts) != 4:
            msg = "권한 실행 오류: 잘못된 동작 형식"
            return ToolResult(text=msg, summary=msg)
        action, subject, relation, object_ = parts
        try:
            if action == "grant":
                await self._fga.grant_tuple(subject, relation, object_)
            elif action == "revoke":
                await self._fga.revoke_tuple(subject, relation, object_)
            else:
                msg = "권한 실행 오류: 알 수 없는 action"
                return ToolResult(text=msg, summary=msg)
            done = f"완료: {planned_action}"
            return ToolResult(text=done, summary=done)
        except Exception as exc:
            msg = f"권한 실행 오류: {type(exc).__name__}"
            return ToolResult(text=msg, summary=msg)


def delegated_membership_dept(planned_action: str) -> str | None:
    """부서 멤버십 위임 대상 부서 추출 (ADR-0046).

    planned_action이 `grant|revoke <subject> member department:<Y>` 형태면 부서 id Y를
    반환한다. 그 외(dept_viewer·capability 부여, query, 형식 불일치)는 None.
    게이트(tool_gate_node)가 이 부서의 admin 여부로 위임을 승격할지 판단한다.
    """
    parts = planned_action.split(" ")
    if len(parts) != 4:
        return None
    action, _subject, relation, object_ = parts
    if action not in ("grant", "revoke") or relation != "member":
        return None
    prefix = "department:"
    if not object_.startswith(prefix):
        return None
    return object_[len(prefix):] or None


def delegated_permission(planned_action: str) -> str | None:
    """permission 배정 위임 대상 권한 추출 (ADR-0051).

    `grant|revoke user:<U> holder permission:<X>` 형태(개인 배정)면 권한 id X를 반환한다.
    부서/역할 배정(subject가 user:가 아님)은 정의급이라 None — c_level 전용.
    게이트(tool_gate_node)가 요청자가 X를 보유한 부서의 admin인지로 승격을 판단한다.
    """
    parts = planned_action.split(" ")
    if len(parts) != 4:
        return None
    action, subject, relation, object_ = parts
    if action not in ("grant", "revoke") or relation != "holder":
        return None
    if not subject.startswith("user:"):
        return None
    prefix = "permission:"
    if not object_.startswith(prefix):
        return None
    return object_[len(prefix):] or None


# 권한 조회 스냅샷에 노출할 capability 작업 — (라벨, 위험도). 게이트 매트릭스(core.sql.gate)가
# 위험도→capability 매핑·3-state 판정의 단일 출처이므로 여기선 표시 순서·라벨만 둔다.
_LABEL_EMOJI = {
    "즉시 허용": "✅",
    "사유 기재 후 허용": "⚠️",
    "불가": "❌",
}

_CAPABILITY_DISPLAY = [
    ("SELECT", RISK_SELECT),
    ("대량 SELECT", RISK_BULK_SELECT),
    ("UPDATE/DELETE", RISK_UPDATE_DELETE),
    ("DDL", RISK_DDL),
    ("권한 부여(grant)", RISK_GRANT),
]

_DECISION_LABEL = {
    DECISION_ALLOW: "즉시 허용",
    DECISION_JUSTIFY_AND_APPROVE: "사유 기재 후 허용",
    DECISION_DENY: "불가",
}


async def _resolve_capabilities(check, user_id: str) -> list[tuple[str, str]]:
    """표시 대상 작업별로 gate_decision 판정 → (라벨, 한국어 결정) 목록.

    게이트(core.sql.gate)를 재사용한다 — 매트릭스 복제 없이 단일 출처. 위험도당 FGA check 1~2회.
    위험도별 gate_decision은 서로 독립이므로 gather로 병렬 — _CAPABILITY_DISPLAY 표시 순서 유지.
    """
    decisions = await asyncio.gather(
        *(gate_decision(check, user_id, risk) for _label, risk in _CAPABILITY_DISPLAY)
    )
    return [
        (label, _DECISION_LABEL.get(decision, decision))
        for (label, _risk), (decision, _reason) in zip(_CAPABILITY_DISPLAY, decisions)
    ]


def _format_permission_snapshot(
    uid: str,
    departments: list,
    roles: list,
    folders: list,
    capabilities: list,
    tables: list | None = None,
) -> str:
    dept_text = ", ".join(departments) if departments else "(없음)"
    role_text = ", ".join(roles) if roles else "(없음)"

    if folders:
        folder_lines = "\n".join(f"- {f}" for f in folders)
    else:
        folder_lines = "(없음)"

    if tables:
        table_text = ", ".join(tables)
    else:
        table_text = "(없음)"

    decision_icon = {
        "즉시 허용": "✅",
        "사유 기재 후 허용": "⚠️",
        "불가": "❌",
    }
    cap_rows = "\n".join(
        f"| {label} | {decision_icon.get(decision, '')} {decision} |"
        for label, decision in capabilities
    )

    return (
        f"## 권한 스냅샷\n\n"
        f"**사용자**: {uid}\n"
        f"**소속 부서**: {dept_text}\n"
        f"**역할(role)**: {role_text}\n\n"
        f"### 접근 가능 폴더\n{folder_lines}\n\n"
        f"### 접근 가능 테이블\n{table_text}\n\n"
        f"### SQL/관리 권한\n"
        f"| 작업 | 허용 여부 |\n"
        f"|------|----------|\n"
        f"{cap_rows}"
    )

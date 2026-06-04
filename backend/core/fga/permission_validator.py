"""권한 동작 화이트리스트 검증 (ADR-0029) — LangGraph 불가지.

LLM이 NL을 파싱한 {action, subject, relation, object}를 받아, id 유효성과
타입 정합을 화이트리스트로 검증한다. 통과 시 (subject, relation, object, action)
4-tuple, 실패 시 None. "이미 그 상태인가"는 멱등이라 검증하지 않는다(ADR-0029).
"""
from pathlib import Path

import yaml

# capability relation 화이트리스트 — manage_permission으로 grant 가능한 SQL 권한.
# 매트릭스 정리: 단순 SELECT만 즉시 허용(allow_select), 그 외 위험군은 justify-only(사유·기록 강제).
_CAPABILITY_RELATIONS = {
    "allow_select", "justify_select",
    "justify_bulk_select",
    "justify_update_delete",
    "justify_ddl",
}


class PermissionValidator:
    def __init__(self, *, user_ids: set, departments: set, folders: set) -> None:
        self._user_ids = user_ids
        self._departments = departments
        self._folders = folders

    @classmethod
    def from_config(
        cls,
        users_path: str = "config/users.yaml",
        folders_path: str = "config/folders.yaml",
    ) -> "PermissionValidator":
        users = yaml.safe_load(Path(users_path).read_text())["users"]
        user_ids = {u["user_id"] for u in users if u.get("user_id")}
        departments: set = set()
        for u in users:
            departments |= {d for d in u.get("departments", []) if d}
        folders_raw = yaml.safe_load(Path(folders_path).read_text())["folders"]
        for spec in folders_raw.values():
            spec = spec or {}
            departments |= {d for d in spec.get("dept_viewers", []) if d}
        folders = {p for p in folders_raw.keys() if p}
        return cls(user_ids=user_ids, departments=departments, folders=folders)

    def _strip(self, value: str, prefix: str) -> str | None:
        return value[len(prefix):] if value.startswith(prefix) else None

    def validate(self, parsed: dict) -> tuple | None:
        action = parsed.get("action")
        subject = parsed.get("subject", "")
        relation = parsed.get("relation", "")
        object_ = parsed.get("object", "")
        if action not in ("grant", "revoke"):
            return None
        # None/비문자열 타입 가드 — LLM이 JSON null을 반환해도 fail-closed.
        if not all(isinstance(x, str) for x in (subject, relation, object_)):
            return None
        # 공백 주입 방어 — 모든 토큰은 공백 없는 id.
        if any(" " in x for x in (subject, relation, object_)):
            return None

        if relation == "member":
            uid = self._strip(subject, "user:")
            dept = self._strip(object_, "department:")
            if uid not in self._user_ids or dept not in self._departments:
                return None
        elif relation == "dept_viewer":
            dept = self._strip(subject, "department:")
            if dept is not None and dept.endswith("#member"):
                dept = dept[: -len("#member")]
            else:
                return None
            path = self._strip(object_, "folder:")
            if dept not in self._departments or path not in self._folders:
                return None
        elif relation in _CAPABILITY_RELATIONS:
            if object_ != "capability:sql":
                return None
            uid = self._strip(subject, "user:")
            if uid in self._user_ids:
                pass
            else:
                dept = self._strip(subject, "department:")
                if dept is not None and dept.endswith("#member"):
                    dept = dept[: -len("#member")]
                else:
                    return None
                if dept not in self._departments:
                    return None
        else:
            return None

        return (subject, relation, object_, action)

    def catalog_text(self) -> str:
        """LLM 파싱 프롬프트에 주입할 알려진 id 목록(정확한 id 유도용)."""
        users = ", ".join(sorted(self._user_ids))
        depts = ", ".join(sorted(self._departments))
        folders = ", ".join(sorted(self._folders))
        return f"유저: {users}\n부서: {depts}\n폴더: {folders}"

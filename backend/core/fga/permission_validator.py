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

# 접근 권한 관리 대상 테이블 화이트리스트 (ADR-0047, seed_fga._TABLE_GRANTS와 동기화).
# DB 스키마가 고정된 환경에서 코드 상수로 관리. 새 테이블 추가 시 여기에 추가 후 seed 재실행.
_KNOWN_TABLES = {"employees", "sales"}


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

    def _resolve_user(self, token: str | None) -> str | None:
        """비격식 user 참조를 정식 "user:<id>"로 결정론적 정규화 (ADR-0031 후속).

        진실원천은 _user_ids 뿐 — 화이트리스트 확장 금지. "user:" 접두는 떼고 본문만 매칭한다.
        후보 수집 규칙(합집합):
          1) 정확 일치        (uid == body)              # 이미 정식 id
          2) "user-" 접두 보정 (uid == "user-" + body)    # "alice" → "user-alice"
          3) 접미 일치        (uid endswith "-" + body)  # "...-alice"
        모든 규칙의 후보를 한 집합으로 모은 뒤 유일할 때만 정식 id를 채택한다.
        후보가 0개(미지)거나 2개 이상(모호)이면 None — fail-closed, 절대 추측 금지.
        """
        if not isinstance(token, str):
            return None
        body = self._strip(token, "user:")
        if body is None:
            body = token
        if not body:
            return None
        candidates = {
            uid
            for uid in self._user_ids
            if uid == body or uid == "user-" + body or uid.endswith("-" + body)
        }
        if len(candidates) == 1:
            return "user:" + next(iter(candidates))
        return None

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
            resolved = self._resolve_user(subject)
            dept = self._strip(object_, "department:")
            if resolved is None or dept not in self._departments:
                return None
            subject = resolved
        elif relation == "dept_viewer" and object_.startswith("table:"):
            table = self._strip(object_, "table:")
            if table not in _KNOWN_TABLES:
                return None
            resolved = self._resolve_user(subject)
            if resolved is not None:
                subject = resolved
            else:
                dept = self._strip(subject, "department:")
                if dept is not None and dept.endswith("#member"):
                    dept = dept[: -len("#member")]
                else:
                    return None
                if dept not in self._departments:
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
            resolved = self._resolve_user(subject)
            if resolved is not None:
                subject = resolved
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
        tables = ", ".join(sorted(_KNOWN_TABLES))
        return f"유저: {users}\n부서: {depts}\n폴더: {folders}\n테이블: {tables}"

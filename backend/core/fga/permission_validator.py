"""권한 동작 화이트리스트 검증 (ADR-0029/ADR-0051) — LangGraph 불가지.

LLM이 NL을 파싱한 {action, subject, relation, object}를 받아, id 유효성과
타입 정합을 화이트리스트로 검증한다. 통과 시 (subject, relation, object, action)
4-tuple, 실패 시 None. "이미 그 상태인가"는 멱등이라 검증하지 않는다(ADR-0029).

grant 종류:
  - member   : 부서 멤버십  (subject=user, object=department:<name>)
  - holder   : permission 배정 (subject=user|department#member|role#member,
                                 object=permission:<name>)
permission 정의(gated_by/capability)는 permissions.yaml 재시드로 관리 —
NL grant 대상이 아니므로 validator 범위 밖.
"""
from pathlib import Path

import yaml


class PermissionValidator:
    def __init__(
        self,
        *,
        user_ids: set,
        departments: set,
        permissions: set,
        names: dict | None = None,
    ) -> None:
        self._user_ids = user_ids
        self._departments = departments
        self._permissions = permissions
        # display_name(예: "오대수") → user_id(예: "user-daesu"). 이름→id 해석용.
        self._names = names or {}

    @classmethod
    def from_config(
        cls,
        users_path: str = "config/users.yaml",
        permissions_path: str = "config/permissions.yaml",
    ) -> "PermissionValidator":
        users = yaml.safe_load(Path(users_path).read_text())["users"]
        user_ids = {u["user_id"] for u in users if u.get("user_id")}
        names = {
            u["display_name"]: u["user_id"]
            for u in users
            if u.get("display_name") and u.get("user_id")
        }
        departments: set = set()
        for u in users:
            departments |= {d for d in u.get("departments", []) if d}
        perms_raw = yaml.safe_load(Path(permissions_path).read_text())["permissions"]
        permissions = {name for name in perms_raw.keys() if name}
        return cls(user_ids=user_ids, departments=departments, permissions=permissions, names=names)

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

    def resolve_user_id(self, token: str | None) -> str | None:
        """자유 형식 user 참조 → 정식 bare user_id(예: "user-daesu") 또는 None.

        도구가 LLM이 만든 user 식별자(접두 불일치·이름 로마자 환각)를 신뢰하지 않도록
        서버측에서 결정론적으로 정규화한다(데모 ⑪⑬⑮ 버그 수정).
        해석 순서: display_name 정확 일치 → id 형태(_resolve_user). 불가 시 None(fail-closed).
        """
        if not isinstance(token, str) or not token.strip():
            return None
        t = token.strip()
        if t in self._names:  # 1) 한국어 표시명: "오대수" → user-daesu
            return self._names[t]
        resolved = self._resolve_user(t)  # 2) id 형태: "user:user-mido"/"mido" → "user:user-mido"
        return resolved[len("user:"):] if resolved is not None else None

    def is_known_user_id(self, uid: str) -> bool:
        return uid in self._user_ids

    def user_catalog_text(self) -> str:
        """LLM 도구 설명에 주입할 "id(이름)" 카탈로그 — 정확한 대상 유저 유도용."""
        id_to_name = {uid: nm for nm, uid in self._names.items()}
        parts = [
            f"{uid}({id_to_name[uid]})" if uid in id_to_name else uid
            for uid in sorted(self._user_ids)
        ]
        return ", ".join(parts)

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
        elif relation == "holder":
            perm = self._strip(object_, "permission:")
            if perm not in self._permissions:
                return None
            resolved = self._resolve_user(subject)
            if resolved is not None:
                subject = resolved
            else:
                if subject.startswith("department:") and subject.endswith("#member"):
                    dept = subject[len("department:"):-len("#member")]
                    if dept not in self._departments:
                        return None
                elif subject.startswith("role:") and subject.endswith("#member"):
                    pass  # 역할 묶음(c_level 등) — 전역 역할은 소수·고정, id 검증 생략
                else:
                    return None
        else:
            return None

        return (subject, relation, object_, action)

    def catalog_text(self) -> str:
        """LLM 파싱 프롬프트에 주입할 알려진 id 목록(정확한 id 유도용)."""
        users = ", ".join(sorted(self._user_ids))
        depts = ", ".join(sorted(self._departments))
        perms = ", ".join(sorted(self._permissions))
        return f"유저: {users}\n부서: {depts}\n권한(permission): {perms}"

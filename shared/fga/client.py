from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


class FGAClient:
    def __init__(self, config: FGAConfig, cache: PermissionCacheBackend) -> None:
        self._config = config
        self._cache = cache

    def build_chroma_filter(self, perm: UserPermission) -> dict:
        clauses: list[dict] = [{"sensitivity": "public"}]
        if perm.teams:
            clauses.append({
                "$and": [
                    {"team_id": {"$in": perm.teams}},
                    {"sensitivity": "internal"},
                ]
            })
        if perm.personal_docs:
            clauses.append({
                "$and": [
                    {"sensitivity": "secret"},
                    {"document_id": {"$in": perm.personal_docs}},
                ]
            })
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}

    def get_permission(self, user_id: str) -> UserPermission:
        raise NotImplementedError("Task 6에서 구현")

    def write_tuples(
        self, doc_id: str, owner_id: str, team_id: str, sensitivity: str
    ) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def delete_user_tuples(self, user_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")

    def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        raise NotImplementedError("Task 6에서 구현")

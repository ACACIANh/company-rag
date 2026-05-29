from typing import TypedDict


class AuthUser(TypedDict):
    user_id: str
    roles: list[str]
    teams: list[str]
    allowed_doc_ids: list[str]

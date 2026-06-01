from typing import TypedDict


class AuthUser(TypedDict):
    user_id: str
    roles: list[str]
    departments: list[str]

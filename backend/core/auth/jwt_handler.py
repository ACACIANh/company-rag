from datetime import datetime, timedelta, timezone

import jwt


def create_token(
    user_id: str,
    roles: list[str],
    departments: list[str],
    secret: str,
    expire_minutes: int,
    display_name: str = "",
) -> str:
    payload = {
        "sub": user_id,
        "roles": roles,
        "departments": departments,
        "display_name": display_name,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])

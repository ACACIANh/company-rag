from datetime import datetime, timedelta, timezone

import jwt


def create_token(
    user_id: str,
    roles: list[str],
    allowed_doc_ids: list[str],
    secret: str,
    expire_minutes: int,
) -> str:
    payload = {
        "sub": user_id,
        "roles": roles,
        "allowed_doc_ids": allowed_doc_ids,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from shared.auth.base import AuthUser
from shared.auth.jwt_handler import decode_token
from shared.config import load_config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_config = load_config()


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
    try:
        payload = decode_token(token, secret=_config.jwt_secret)
        return AuthUser(
            user_id=payload["sub"],
            roles=payload["roles"],
            allowed_doc_ids=payload["allowed_doc_ids"],
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if "admin" not in user["roles"]:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user

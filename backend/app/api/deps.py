import logging

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from core.auth.base import AuthUser
from core.auth.jwt_handler import decode_token
from core.config import load_config
from core.fga.client import FGAClient
from core.rate_limiter.in_memory import InMemoryRateLimiter
from core.session.base import SessionStore

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_config = load_config()
_rate_limiter = InMemoryRateLimiter(
    rules={"/chat": _config.rate_limit_per_minute},
    default_limit=_config.rate_limit_per_minute,
)


def get_fga_client(request: Request) -> FGAClient:
    return request.app.state.fga_client


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_original_store(request: Request):
    return request.app.state.original_store


def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
    try:
        payload = decode_token(token, secret=_config.jwt_secret)
        return AuthUser(
            user_id=payload["sub"],
            roles=payload["roles"],
            departments=payload.get("departments", []),
        )
    except (jwt.InvalidTokenError, KeyError) as exc:
        logger.warning("token rejected: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if "admin" not in user["roles"]:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def check_rate_limit(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> None:
    if not _rate_limiter.is_allowed(user["user_id"], request.url.path):
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": "60"},
        )

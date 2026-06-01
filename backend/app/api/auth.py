from pathlib import Path

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.auth.base import AuthUser
from core.auth.jwt_handler import create_token
from core.config import load_config
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

_config = load_config()


def _load_users() -> list[dict]:
    path = Path("config/users.yaml")
    return yaml.safe_load(path.read_text())["users"]


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
def login(req: TokenRequest) -> TokenResponse:
    from fastapi import HTTPException
    users = _load_users()
    user = next(
        (u for u in users if u["username"] == req.username and u["password"] == req.password),
        None,
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(
        user_id=user["user_id"],
        roles=user["roles"],
        departments=user.get("departments", []),
        secret=_config.jwt_secret,
        expire_minutes=_config.jwt_expire_minutes,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=dict)
def me(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return dict(current_user)

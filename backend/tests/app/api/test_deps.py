import pytest
from fastapi import HTTPException

from core.auth.jwt_handler import create_token
from app.api import deps


def _token(expire_minutes: int) -> str:
    return create_token(
        user_id="u1",
        roles=["member"],
        departments=["t1"],
        secret=deps._config.jwt_secret,
        expire_minutes=expire_minutes,
    )


def test_get_current_user_accepts_valid_token():
    user = deps.get_current_user(token=_token(60))
    assert user["user_id"] == "u1"
    assert user["departments"] == ["t1"]


def test_get_current_user_extracts_display_name():
    token = create_token(
        user_id="u1", roles=["member"], departments=["t1"],
        secret=deps._config.jwt_secret, expire_minutes=60, display_name="노주환",
    )
    user = deps.get_current_user(token=token)
    assert user["display_name"] == "노주환"


def test_get_current_user_display_name_falls_back_to_user_id():
    # display_name 클레임이 없는 옛 토큰도 안전하게 동작해야 한다.
    user = deps.get_current_user(token=_token(60))
    assert user["display_name"] == "u1"


def test_get_current_user_rejects_malformed_token():
    with pytest.raises(HTTPException) as exc:
        deps.get_current_user(token="not-a-jwt")
    assert exc.value.status_code == 401


def test_get_current_user_rejects_expired_token():
    with pytest.raises(HTTPException) as exc:
        deps.get_current_user(token=_token(-1))
    assert exc.value.status_code == 401


def test_get_current_user_rejects_wrong_secret_signature():
    bad = create_token(
        user_id="u1", roles=["member"], departments=[],
        secret="some-other-secret-not-matching", expire_minutes=60,
    )
    with pytest.raises(HTTPException) as exc:
        deps.get_current_user(token=bad)
    assert exc.value.status_code == 401

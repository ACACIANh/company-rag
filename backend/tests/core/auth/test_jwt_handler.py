import pytest
from core.auth.jwt_handler import create_token, decode_token


def test_create_and_decode_token():
    token = create_token(
        user_id="user-alice",
        roles=["user"],
        departments=["engineering", "all"],
        secret="test-secret",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == "user-alice"
    assert payload["roles"] == ["user"]
    assert payload["departments"] == ["engineering", "all"]
    assert "allowed_doc_ids" not in payload


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not.a.valid.token", secret="test-secret")


def test_decode_wrong_secret_raises():
    token = create_token(
        user_id="u1",
        roles=["user"],
        departments=[],
        secret="secret-a",
        expire_minutes=60,
    )
    with pytest.raises(Exception):
        decode_token(token, secret="secret-b")


def test_departments_encoded_and_decoded():
    token = create_token(
        user_id="u1",
        roles=["user"],
        departments=["engineering"],
        secret="s",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="s")
    assert payload["departments"] == ["engineering"]


def test_empty_departments_encoded():
    token = create_token(
        user_id="u1",
        roles=["admin"],
        departments=[],
        secret="s",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="s")
    assert payload["departments"] == []

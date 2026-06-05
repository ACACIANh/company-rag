import pytest
from core.auth.jwt_handler import create_token, decode_token


def test_create_and_decode_token():
    token = create_token(
        user_id="user-jisoo",
        roles=["user"],
        departments=["개발", "all"],
        secret="test-secret",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == "user-jisoo"
    assert payload["roles"] == ["user"]
    assert payload["departments"] == ["개발", "all"]
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
        departments=["개발"],
        secret="s",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="s")
    assert payload["departments"] == ["개발"]


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


def test_display_name_encoded_and_decoded():
    token = create_token(
        user_id="u1",
        roles=["user"],
        departments=[],
        secret="s",
        expire_minutes=60,
        display_name="김지수",
    )
    payload = decode_token(token, secret="s")
    assert payload["display_name"] == "김지수"

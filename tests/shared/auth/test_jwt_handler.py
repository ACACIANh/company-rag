import pytest
from shared.auth.jwt_handler import create_token, decode_token


def test_create_and_decode_token():
    token = create_token(
        user_id="user-alice",
        roles=["user"],
        allowed_doc_ids=["docs/company/policy.md"],
        secret="test-secret",
        expire_minutes=60,
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == "user-alice"
    assert payload["roles"] == ["user"]
    assert payload["allowed_doc_ids"] == ["docs/company/policy.md"]


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("not.a.valid.token", secret="test-secret")


def test_decode_wrong_secret_raises():
    token = create_token("u1", ["user"], [], secret="secret-a", expire_minutes=60)
    with pytest.raises(Exception):
        decode_token(token, secret="secret-b")

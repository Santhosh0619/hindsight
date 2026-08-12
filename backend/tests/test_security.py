import time

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    password = "correct horse battery staple"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")

    assert verify_password("wrong password", hashed) is False


def test_generate_refresh_token_is_unique_and_opaque() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first != second
    assert len(first) > 32


def test_hash_refresh_token_is_deterministic() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert hash_refresh_token(token) != token


def test_access_token_roundtrip() -> None:
    token = create_access_token(user_id="user-123", workspace_id="ws-456")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["workspace_id"] == "ws-456"
    assert payload["type"] == "access"


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token(user_id="user-123")
    # exp is an int-seconds claim once encoded; forge one already in the past.
    payload = jwt.decode(token, options={"verify_signature": False})
    payload["exp"] = int(time.time()) - 10

    from app.core.config import get_settings

    expired_token = jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)

import pytest

from app.services.auth import AuthError, create_access_token, decode_auth_header


def test_decode_auth_header_ok() -> None:
    token = create_access_token(sub="tester")
    payload = decode_auth_header(f"Bearer {token}")

    assert payload["sub"] == "tester"
    assert payload["role"] == "user"


def test_decode_auth_header_missing() -> None:
    with pytest.raises(AuthError):
        decode_auth_header(None)

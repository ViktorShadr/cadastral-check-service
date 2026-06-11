import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings

JWT_ALGORITHM = "HS256"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 210_000


class InvalidTokenError(Exception):
    """Raised when a JWT cannot be trusted or is expired."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PBKDF2_ITERATIONS),
            _base64url_encode(salt),
            _base64url_encode(password_hash),
        ]
    )


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_hash = hashed_password.split(
            "$",
            3,
        )
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _base64url_decode(salt_text),
            int(iterations_text),
        )
    except (binascii.Error, ValueError, TypeError):
        return False

    return hmac.compare_digest(_base64url_encode(password_hash), expected_hash)


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return _encode_jwt(payload, settings.jwt_secret_key)


def decode_access_token(token: str, settings: Settings) -> int:
    try:
        header_text, payload_text, signature_text = token.split(".")
        signed_part = f"{header_text}.{payload_text}".encode("ascii")
        expected_signature = _sign(signed_part, settings.jwt_secret_key)
    except ValueError as exc:
        raise InvalidTokenError from exc

    if not hmac.compare_digest(expected_signature, signature_text):
        raise InvalidTokenError

    try:
        header = json.loads(_base64url_decode(header_text))
        payload = json.loads(_base64url_decode(payload_text))
    except (binascii.Error, ValueError, TypeError) as exc:
        raise InvalidTokenError from exc

    if header.get("alg") != JWT_ALGORITHM or payload.get("type") != "access":
        raise InvalidTokenError

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(
        datetime.now(UTC).timestamp()
    ):
        raise InvalidTokenError

    subject = payload.get("sub")
    try:
        return int(subject)
    except (TypeError, ValueError) as exc:
        raise InvalidTokenError from exc


def _encode_jwt(payload: dict[str, Any], secret_key: str) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_text = _base64url_encode(_json_bytes(header))
    payload_text = _base64url_encode(_json_bytes(payload))
    signed_part = f"{header_text}.{payload_text}".encode("ascii")
    signature_text = _sign(signed_part, secret_key)
    return f"{header_text}.{payload_text}.{signature_text}"


def _sign(value: bytes, secret_key: str) -> str:
    signature = hmac.new(secret_key.encode("utf-8"), value, hashlib.sha256).digest()
    return _base64url_encode(signature)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")

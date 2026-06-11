"""Password hashing and JWT helpers for authentication flows."""

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
    """Hash a plain-text password with PBKDF2 and a random salt.

    Args:
        password: Plain-text password supplied by a user.

    Returns:
        Encoded password hash containing algorithm, iterations, salt, and digest.
    """
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
    """Check whether a plain-text password matches a stored password hash.

    Args:
        password: Plain-text password supplied during authentication.
        hashed_password: Stored password hash produced by hash_password.

    Returns:
        True when the password matches the stored hash, otherwise False.
    """
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
    """Create a signed access token for an authenticated user.

    Args:
        user_id: Database identifier of the authenticated user.
        settings: Runtime settings containing JWT secret and expiration.

    Returns:
        Compact JWT string that can be used as a bearer token.
    """
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
    """Validate an access token and extract its user identifier.

    Args:
        token: Bearer token received from a client.
        settings: Runtime settings containing the JWT secret.

    Returns:
        User identifier stored in the token subject.

    Raises:
        InvalidTokenError: If the token is malformed, expired, or has a bad
            signature.
    """
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
    """Serialize and sign a JWT payload.

    Args:
        payload: Claims to encode into the token body.
        secret_key: Shared secret used to sign the token.

    Returns:
        Signed compact JWT string.
    """
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_text = _base64url_encode(_json_bytes(header))
    payload_text = _base64url_encode(_json_bytes(payload))
    signed_part = f"{header_text}.{payload_text}".encode("ascii")
    signature_text = _sign(signed_part, secret_key)
    return f"{header_text}.{payload_text}.{signature_text}"


def _sign(value: bytes, secret_key: str) -> str:
    """Create a base64url-encoded HMAC signature.

    Args:
        value: Bytes that must be authenticated.
        secret_key: Shared secret used for HMAC signing.

    Returns:
        Base64url-encoded signature without padding.
    """
    signature = hmac.new(secret_key.encode("utf-8"), value, hashlib.sha256).digest()
    return _base64url_encode(signature)


def _json_bytes(value: dict[str, Any]) -> bytes:
    """Encode JSON data in a deterministic byte representation.

    Args:
        value: JSON-compatible dictionary to encode.

    Returns:
        UTF-8 encoded JSON bytes with stable key ordering.
    """
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _base64url_encode(value: bytes) -> str:
    """Encode bytes with URL-safe base64 without padding.

    Args:
        value: Raw bytes to encode.

    Returns:
        ASCII base64url string without trailing padding.
    """
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    """Decode a URL-safe base64 string that may omit padding.

    Args:
        value: Base64url string to decode.

    Returns:
        Decoded raw bytes.

    Raises:
        binascii.Error: If the encoded value is invalid.
    """
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")

"""Reusable FastAPI dependencies for settings and authenticated users."""

from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.security import InvalidTokenError, decode_access_token
from app.schemas import UserInDB

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    """Return application settings stored in FastAPI state.

    Args:
        request: Incoming request with access to the application state.

    Returns:
        Runtime settings shared across API and service layers.
    """
    return request.app.state.settings


def auth_error(detail: str = "Not authenticated.") -> HTTPException:
    """Build a standardized bearer authentication error.

    Args:
        detail: Error message returned to the client.

    Returns:
        HTTPException configured with a WWW-Authenticate header.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> UserInDB:
    """Resolve the active user from a bearer token.

    Args:
        request: Incoming request carrying app state and database pool.
        credentials: Optional HTTP bearer credentials extracted by FastAPI.

    Returns:
        Active user record loaded from the database.

    Raises:
        HTTPException: If credentials are missing, invalid, expired, or belong
            to an inactive user.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_error()

    settings = get_settings(request)
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        raise auth_error("Invalid or expired token.") from exc

    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                email,
                hashed_password,
                is_active,
                is_admin,
                created_at
            FROM users
            WHERE id = $1
            """,
            user_id,
        )

    if row is None:
        raise auth_error("Invalid or expired token.")

    user = UserInDB(**dict(row))
    if not user.is_active:
        raise auth_error("Inactive user.")

    return user


async def get_current_admin_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> UserInDB:
    """Require the authenticated user to have administrator privileges.

    Args:
        current_user: Active user resolved by get_current_user.

    Returns:
        Authenticated administrator user.

    Raises:
        HTTPException: If the current user is not an administrator.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    return current_user

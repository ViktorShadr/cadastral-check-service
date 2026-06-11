from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.security import InvalidTokenError, decode_access_token
from app.schemas import UserInDB

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def auth_error(detail: str = "Not authenticated.") -> HTTPException:
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

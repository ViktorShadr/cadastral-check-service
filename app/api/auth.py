from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user, get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas import LoginRequest, RegisterRequest, Token, UserInDB, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, request: Request) -> UserPublic:
    pool: asyncpg.Pool = request.app.state.db_pool
    hashed_password = hash_password(payload.password)

    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO users (email, hashed_password)
                VALUES ($1, $2)
                RETURNING
                    id,
                    email,
                    is_active,
                    is_admin,
                    created_at
                """,
                payload.email,
                hashed_password,
            )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from exc

    return UserPublic(**dict(row))


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, request: Request) -> Token:
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
            WHERE email = $1
            """,
            payload.email,
        )

    if row is None:
        raise_invalid_credentials()

    user = UserInDB(**dict(row))
    if not user.is_active or not verify_password(
        payload.password, user.hashed_password
    ):
        raise_invalid_credentials()

    settings = get_settings(request)
    return Token(access_token=create_access_token(user.id, settings))


@router.get("/me", response_model=UserPublic)
async def me(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> UserPublic:
    return to_public_user(current_user)


def raise_invalid_credentials() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def to_public_user(user: UserInDB) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )

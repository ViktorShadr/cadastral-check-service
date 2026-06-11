from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.api.dependencies import get_current_admin_user
from app.schemas import AdminHistoryItem, OptionalCadastralNumber, UserInDB, UserPublic

router = APIRouter(prefix="/admin", tags=["admin"])
DEFAULT_ADMIN_LIMIT = 100
MAX_ADMIN_LIMIT = 500


@router.get("/users", response_model=list[UserPublic])
async def users(
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserPublic]:
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                id,
                email,
                is_active,
                is_admin,
                created_at
            FROM users
            ORDER BY created_at DESC, id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return [UserPublic(**dict(row)) for row in rows]


@router.get("/history", response_model=list[AdminHistoryItem])
async def history(
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
    cadastral_number: Annotated[
        OptionalCadastralNumber,
        Query(),
    ] = None,
    user_id: Annotated[int | None, Query(ge=1)] = None,
    result: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_ADMIN_LIMIT)] = DEFAULT_ADMIN_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminHistoryItem]:
    pool: asyncpg.Pool = request.app.state.db_pool
    query_text = """
        SELECT
            id,
            user_id,
            cadastral_number,
            latitude,
            longitude,
            result,
            created_at
        FROM request_history
    """
    query_args: list[object] = []
    where_clauses: list[str] = []

    if cadastral_number is not None:
        query_args.append(cadastral_number)
        where_clauses.append(f"cadastral_number = ${len(query_args)}")

    if user_id is not None:
        query_args.append(user_id)
        where_clauses.append(f"user_id = ${len(query_args)}")

    if result is not None:
        query_args.append(result)
        where_clauses.append(f"result = ${len(query_args)}")

    if where_clauses:
        query_text += " WHERE " + " AND ".join(where_clauses)

    limit_placeholder = len(query_args) + 1
    offset_placeholder = len(query_args) + 2
    query_text += (
        f" ORDER BY created_at DESC, id DESC LIMIT ${limit_placeholder}"
        f" OFFSET ${offset_placeholder}"
    )
    query_args.extend([limit, offset])

    async with pool.acquire() as connection:
        rows = await connection.fetch(query_text, *query_args)

    return [AdminHistoryItem(**dict(row)) for row in rows]


@router.get("/history/{request_id}", response_model=AdminHistoryItem)
async def history_item(
    request_id: Annotated[int, Path(ge=1)],
    request: Request,
    _current_admin_user: Annotated[UserInDB, Depends(get_current_admin_user)],
) -> AdminHistoryItem:
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                user_id,
                cadastral_number,
                latitude,
                longitude,
                result,
                created_at
            FROM request_history
            WHERE id = $1
            """,
            request_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History request not found.",
        )

    return AdminHistoryItem(**dict(row))

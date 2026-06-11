from typing import Annotated

import asyncpg
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.api.dependencies import get_current_user, get_settings
from app.schemas import (
    HistoryItem,
    OptionalCadastralNumber,
    QueryRequest,
    QueryResponse,
    UserInDB,
)
from app.services.external_result import (
    ExternalServiceInvalidResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    fetch_external_result,
)

router = APIRouter()
DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 500
DEFAULT_RESULT_PAYLOAD = QueryRequest(
    cadastral_number="77:01:0004012:2054",
    latitude=55.7558,
    longitude=37.6173,
)


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ping/db")
async def ping_db(request: Request) -> dict[str, str]:
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.fetchval("SELECT 1")

    return {"status": "ok"}


@router.get("/result")
@router.post("/result")
async def result(
    request: Request,
    payload: Annotated[QueryRequest | None, Body()] = None,
) -> bool:
    result_payload = payload or DEFAULT_RESULT_PAYLOAD
    return await request_external_result(result_payload, request)


@router.post("/query")
async def query(
    payload: QueryRequest,
    request: Request,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> QueryResponse:
    result_value = await request_external_result(payload, request)
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO request_history (
                user_id,
                cadastral_number,
                latitude,
                longitude,
                result
            )
            VALUES ($1, $2, $3, $4, $5)
            """,
            current_user.id,
            payload.cadastral_number,
            payload.latitude,
            payload.longitude,
            result_value,
        )

    return QueryResponse(result=result_value)


async def request_external_result(payload: QueryRequest, request: Request) -> bool:
    settings = get_settings(request)

    try:
        return await fetch_external_result(payload, settings)
    except ExternalServiceTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="External service request timed out.",
        ) from exc
    except ExternalServiceUnavailableError as exc:
        raise HTTPException(
            status_code=502,
            detail="External service is unavailable.",
        ) from exc
    except ExternalServiceInvalidResponseError as exc:
        raise HTTPException(
            status_code=502,
            detail="External service returned an invalid response.",
        ) from exc


@router.get("/history")
async def history(
    request: Request,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    cadastral_number: Annotated[
        OptionalCadastralNumber,
        Query(),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_HISTORY_LIMIT),
    ] = DEFAULT_HISTORY_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[HistoryItem]:
    pool: asyncpg.Pool = request.app.state.db_pool
    query_text = """
        SELECT
            id,
            cadastral_number,
            latitude,
            longitude,
            result,
            created_at
        FROM request_history
    """
    query_args: list[object] = []
    where_clauses: list[str] = []

    if not current_user.is_admin:
        query_args.append(current_user.id)
        where_clauses.append(f"user_id = ${len(query_args)}")

    if cadastral_number is not None:
        query_args.append(cadastral_number)
        where_clauses.append(f"cadastral_number = ${len(query_args)}")

    if where_clauses:
        query_text += " WHERE " + " AND ".join(where_clauses)

    limit_placeholder = len(query_args) + 1
    offset_placeholder = len(query_args) + 2
    query_text += (
        f" ORDER BY created_at DESC LIMIT ${limit_placeholder}"
        f" OFFSET ${offset_placeholder}"
    )
    query_args.extend([limit, offset])

    async with pool.acquire() as connection:
        rows = await connection.fetch(query_text, *query_args)

    return [HistoryItem(**dict(row)) for row in rows]

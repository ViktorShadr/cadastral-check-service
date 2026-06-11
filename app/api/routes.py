"""Public API endpoints for cadastral checks and request history."""

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

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


@router.get("/ping")
async def ping() -> dict[str, str]:
    """Report that the HTTP service process is alive.

    Args:
        None

    Returns:
        Status payload with an ok marker.
    """
    return {"status": "ok"}


@router.get("/ping/db")
async def ping_db(request: Request) -> dict[str, str]:
    """Report that the service can reach the configured database.

    Args:
        request: Incoming request with access to the database pool.

    Returns:
        Status payload with an ok marker after a successful database query.

    Raises:
        asyncpg.PostgresError: If the database health query fails.
    """
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.fetchval("SELECT 1")

    return {"status": "ok"}


@router.post("/result")
async def result(
    payload: QueryRequest,
    request: Request,
) -> bool:
    """Proxy a cadastral check to the external result service.

    Args:
        payload: Cadastral check payload to proxy to the external service.
        request: Incoming request with settings used by the service client.

    Returns:
        Boolean result returned by the external service.

    Raises:
        HTTPException: If the external service times out, is unavailable, or
            returns an invalid response.
    """
    return await request_external_result(payload, request)


@router.post("/query")
async def query(
    payload: QueryRequest,
    request: Request,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> QueryResponse:
    """Run an authenticated cadastral check and persist the request history.

    Args:
        payload: Cadastral number and coordinates to check.
        request: Incoming request with settings and database pool.
        current_user: Authenticated user owning the saved history entry.

    Returns:
        Response model containing the external boolean check result.

    Raises:
        HTTPException: If authentication fails or the external service cannot
            produce a valid result.
        asyncpg.PostgresError: If saving request history fails.
    """
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
    """Call the service layer and translate integration errors to HTTP errors.

    Args:
        payload: Cadastral check payload for the external service.
        request: Incoming request with access to runtime settings.

    Returns:
        Boolean result returned by the external result service.

    Raises:
        HTTPException: If the external call times out, is unavailable, or
            returns an invalid response.
    """
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
    """Return cadastral check history visible to the authenticated user.

    Args:
        request: Incoming request with access to the database pool.
        current_user: Authenticated user used to scope non-admin history.
        cadastral_number: Optional cadastral number filter.
        limit: Maximum number of history entries to return.
        offset: Number of matching entries to skip.

    Returns:
        List of history entries ordered from newest to oldest.

    Raises:
        HTTPException: If authentication fails in the dependency.
        asyncpg.PostgresError: If the history query fails.
    """
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

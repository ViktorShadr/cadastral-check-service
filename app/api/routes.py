import asyncio
import random
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Query, Request

from app.schemas import (
    HistoryItem,
    OptionalCadastralNumber,
    QueryRequest,
    QueryResponse,
)

router = APIRouter()
RESULT_DELAY_SECONDS = 0.1
DEFAULT_HISTORY_LIMIT = 100
MAX_HISTORY_LIMIT = 500


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ping/db")
async def ping_db(request: Request) -> dict[str, str]:
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.fetchval("SELECT 1")

    return {"status": "ok"}


async def get_result() -> bool:
    await asyncio.sleep(RESULT_DELAY_SECONDS)
    return random.choice([True, False])


@router.get("/result")
@router.post("/result")
async def result() -> bool:
    return await get_result()


@router.post("/query")
async def query(payload: QueryRequest, request: Request) -> QueryResponse:
    result_value = await get_result()
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO request_history (
                cadastral_number,
                latitude,
                longitude,
                result
            )
            VALUES ($1, $2, $3, $4)
            """,
            payload.cadastral_number,
            payload.latitude,
            payload.longitude,
            result_value,
        )

    return QueryResponse(result=result_value)


@router.get("/history")
async def history(
    request: Request,
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

    if cadastral_number is not None:
        query_text += " WHERE cadastral_number = $1"
        query_args.append(cadastral_number)

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

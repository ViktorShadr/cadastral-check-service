import asyncio
import random
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()
RESULT_DELAY_SECONDS = 0.1


class QueryRequest(BaseModel):
    cadastral_number: str
    latitude: float
    longitude: float


class QueryResponse(BaseModel):
    result: bool


class HistoryItem(BaseModel):
    id: int
    cadastral_number: str
    latitude: float
    longitude: float
    result: bool
    created_at: datetime


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
    cadastral_number: str | None = None,
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
    query_args: tuple[str, ...] = ()

    if cadastral_number is not None:
        query_text += " WHERE cadastral_number = $1"
        query_args = (cadastral_number,)

    query_text += " ORDER BY created_at DESC"

    async with pool.acquire() as connection:
        rows = await connection.fetch(query_text, *query_args)

    return [HistoryItem(**dict(row)) for row in rows]

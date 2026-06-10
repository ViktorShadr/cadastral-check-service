import asyncio
import random

import asyncpg
from fastapi import APIRouter, Request

router = APIRouter()
RESULT_DELAY_SECONDS = 0.1


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

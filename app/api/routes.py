import asyncpg
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ping/db")
async def ping_db(request: Request) -> dict[str, str]:
    pool: asyncpg.Pool = request.app.state.db_pool

    async with pool.acquire() as connection:
        await connection.fetchval("SELECT 1")

    return {"status": "ok"}

import asyncpg

from app.core.config import Settings


async def create_db_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=settings.database_url)


async def close_db_pool(pool: asyncpg.Pool) -> None:
    await pool.close()

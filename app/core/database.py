"""Database connection helpers for the application lifecycle."""

import asyncpg

from app.core.config import Settings


async def create_db_pool(settings: Settings) -> asyncpg.Pool:
    """Create the async PostgreSQL pool used by repositories and endpoints.

    Args:
        settings: Runtime configuration containing the database DSN.

    Returns:
        Initialized asyncpg connection pool.
    """
    return await asyncpg.create_pool(dsn=settings.database_url)


async def close_db_pool(pool: asyncpg.Pool) -> None:
    """Close the shared async PostgreSQL pool during application shutdown.

    Args:
        pool: Connection pool created during application startup.

    Returns:
        None
    """
    await pool.close()

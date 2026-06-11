"""FastAPI application assembly and lifecycle management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.routes import router
from app.core.config import Settings
from app.core.database import close_db_pool, create_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and dispose shared application resources.

    Args:
        app: FastAPI application instance receiving shared state.

    Yields:
        None while the application is serving requests.

    Returns:
        None
    """
    settings = Settings()
    pool = await create_db_pool(settings)

    app.state.settings = settings
    app.state.db_pool = pool

    try:
        yield
    finally:
        await close_db_pool(pool)


app = FastAPI(title="Cadastral Check Service", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(router)

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings
from app.core.database import close_db_pool, create_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    pool = await create_db_pool(settings)

    app.state.settings = settings
    app.state.db_pool = pool

    try:
        yield
    finally:
        await close_db_pool(pool)


app = FastAPI(title="Cadastral Check Service", lifespan=lifespan)
app.include_router(router)

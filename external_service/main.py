"""FastAPI emulator for the external cadastral result provider."""

import asyncio
import random
from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas import QueryRequest, QueryResponse


class ExternalServiceSettings(BaseSettings):
    """Runtime settings for the external-service emulator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="external_service_",
        extra="ignore",
    )

    result_delay_seconds: float = Field(default=0.1, ge=0)


def get_settings() -> ExternalServiceSettings:
    """Load external-service emulator settings from environment variables."""
    return ExternalServiceSettings()


app = FastAPI(title="External Cadastral Result Emulator")


@app.get("/ping")
async def ping() -> dict[str, str]:
    """Report that the external-service process is ready to handle requests."""
    return {"status": "ok"}


@app.post("/result")
async def result(
    payload: QueryRequest,
    settings: Annotated[ExternalServiceSettings, Depends(get_settings)],
) -> QueryResponse:
    """Return a simulated cadastral check result.

    Args:
        payload: Cadastral check request accepted for contract compatibility.
        settings: Runtime settings controlling emulator behavior.

    Returns:
        Response model containing a randomly generated boolean result.
    """
    await asyncio.sleep(settings.result_delay_seconds)
    return QueryResponse(result=random.choice([True, False]))

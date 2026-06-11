import asyncio
import random

from fastapi import FastAPI

from app.schemas import QueryRequest, QueryResponse

RESULT_DELAY_SECONDS = 0.1

app = FastAPI(title="External Cadastral Result Emulator")


@app.post("/result")
async def result(payload: QueryRequest) -> QueryResponse:
    await asyncio.sleep(RESULT_DELAY_SECONDS)
    return QueryResponse(result=random.choice([True, False]))

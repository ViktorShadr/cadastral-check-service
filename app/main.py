from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Cadastral Check Service")
app.include_router(router)

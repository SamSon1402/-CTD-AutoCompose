"""CTD-AutoCompose API entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import settings
from app.store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    yield
    await store.disconnect()


app = FastAPI(
    title="CTD-AutoCompose API",
    description=(
        "ICH eCTD submission drafting service. "
        "Ingest CSRs, protocols, SAPs → generate regulator-ready CTD sections with traced citations."
    ),
    version="0.4.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)

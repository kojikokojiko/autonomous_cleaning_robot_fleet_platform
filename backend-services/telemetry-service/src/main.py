import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.telemetry import router as telemetry_router
from src.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Telemetry service started")
    yield
    await engine.dispose()
    logger.info("Telemetry service stopped")


app = FastAPI(
    title="Telemetry Service",
    description="TimescaleDB telemetry query API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "telemetry-service"}

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.robots import router as robots_router
from src.db.session import engine
from src.db.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev only; use Alembic in prod)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Fleet service started")
    yield
    await engine.dispose()
    logger.info("Fleet service stopped")


app = FastAPI(
    title="Fleet Service",
    description="Robot fleet management API",
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

app.include_router(robots_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fleet-service"}

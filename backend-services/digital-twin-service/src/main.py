from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.twins import router as twins_router
from src.db.models import Base
from src.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Digital twin service started")
    yield
    await engine.dispose()
    logger.info("Digital twin service stopped")


app = FastAPI(
    title="Digital Twin Service",
    description="Robot digital twin state management API",
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

app.include_router(twins_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "digital-twin-service"}

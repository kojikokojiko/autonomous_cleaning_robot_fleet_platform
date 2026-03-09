import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.missions import router as missions_router
from src.db.session import engine
from src.db.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Mission service started")
    yield
    await engine.dispose()


app = FastAPI(
    title="Mission Service",
    description="Mission scheduling and task allocation API",
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

app.include_router(missions_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mission-service"}

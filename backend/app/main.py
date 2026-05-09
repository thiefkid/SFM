from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import create_tables
from app.api.routes import refresh as refresh_router


scheduler = AsyncIOScheduler(timezone="US/Eastern")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — skip DB when mock mode is on (no PostgreSQL needed)
    if not settings.scraper_mock_mode:
        await create_tables()

        from app.services.historical import update_all_known_symbols
        scheduler.add_job(
            update_all_known_symbols,
            "cron",
            hour=settings.nightly_update_hour,
            minute=settings.nightly_update_minute,
            id="nightly_price_update",
            replace_existing=True,
        )
        scheduler.start()

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="SFM Stock Pick Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(refresh_router.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

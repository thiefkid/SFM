import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import create_tables, async_session
from app.api.routes import refresh as refresh_router

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="US/Eastern")
_db_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_ready
    if not settings.scraper_mock_mode:
        try:
            # Neon free tier can be slow to wake; 60s gives it room
            await asyncio.wait_for(create_tables(), timeout=60)
            _db_ready = True
        except asyncio.TimeoutError:
            logger.error("DB create_tables timed out after 60s — check DATABASE_URL")
        except Exception as exc:
            logger.error("DB create_tables failed: %s", exc)

        if _db_ready:
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

    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="SFM Stock Pick Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(refresh_router.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    if settings.scraper_mock_mode:
        return {"status": "ok"}
    if not _db_ready:
        return {"status": "error", "detail": "DB not initialized on startup"}
    try:
        async with async_session() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=5)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

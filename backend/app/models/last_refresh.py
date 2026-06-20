from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LastRefresh(Base):
    """Single-row snapshot of the most recent /refresh result.

    The /last endpoint reads from here so the dashboard survives Cloud Run cold
    starts and redeploys (the in-memory cache is wiped every time the instance
    is reclaimed). Payload is the RefreshResponse serialised as JSON text —
    portable across Postgres/SQLite without JSONB-specific handling.
    """

    __tablename__ = "last_refresh"

    # Always row id=1 — we keep only the latest snapshot (upsert in place).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

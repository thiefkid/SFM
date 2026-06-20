from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LastRefresh(Base):
    __tablename__ = "last_refresh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Distributed lock: is_refreshing acts as a single-flight guard across all
    # Cloud Run instances. refresh_started_at lets a stuck lock (crashed/hung
    # refresh) be stolen after a staleness timeout so it can't wedge forever.
    is_refreshing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    refresh_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

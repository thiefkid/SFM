from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LastRefresh(Base):
    __tablename__ = "last_refresh"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_refreshing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

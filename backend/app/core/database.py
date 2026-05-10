from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Normalize plain postgresql:// → postgresql+asyncpg://
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgres://"):]
elif _db_url.startswith("postgresql://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgresql://"):]

# asyncpg doesn't understand libpq query params (sslmode, channel_binding, etc.).
# Strip all query params and pass ssl=require directly for any non-local host.
_parsed = urlparse(_db_url)
_is_local = _parsed.hostname in (None, "localhost", "127.0.0.1", "::1")
_db_url = urlunparse(_parsed._replace(query=""))
_connect_args: dict = {} if _is_local else {"ssl": "require"}

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=60,    # recycle connections after 60s to avoid Neon idle drops
    pool_timeout=30,
    connect_args=_connect_args,
)
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[return]
    async with async_session() as session:
        yield session

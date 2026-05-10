from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Normalize plain postgresql:// → postgresql+asyncpg:// so a Neon/Supabase
# URL copied verbatim still works without editing the secret.
_db_url = settings.database_url
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgres://"):]
elif _db_url.startswith("postgresql://"):
    _db_url = "postgresql+asyncpg://" + _db_url[len("postgresql://"):]

# asyncpg doesn't accept sslmode (a libpq/psycopg2 concept); strip it and
# map the value to asyncpg's ssl connect_arg instead.
_connect_args: dict = {}
if "sslmode=" in _db_url:
    parsed = urlparse(_db_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = qs.pop("sslmode", ["require"])[0]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    _db_url = urlunparse(parsed._replace(query=new_query))
    if sslmode in ("require", "verify-ca", "verify-full"):
        _connect_args["ssl"] = "require"
    elif sslmode in ("prefer", "allow"):
        _connect_args["ssl"] = True

engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True, connect_args=_connect_args)
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

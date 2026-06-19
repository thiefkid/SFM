"""
Historical daily price service.

Uses yfinance to fetch and store full price history per symbol.
Data is stored in the daily_prices table and used for:
  - I4: past 15 trading days' trading value (bar chart)
  - I5: all-time high (ATH) price and date + 52-week high
"""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from sqlalchemy import select, text

from app.core.database import async_session
from app.models.daily_price import DailyPrice


# US market timezone + regular-session bounds (regular hours: 09:30–16:00 ET)
ET = ZoneInfo("America/New_York")
_MARKET_OPEN = (9, 30)
_MARKET_CLOSE = (16, 0)


def _now_et() -> datetime:
    return datetime.now(ET)


def _session_started(now_et: datetime) -> bool:
    """
    True from the opening bell onward on a weekday (holidays not accounted for).

    Note this stays true *after* the close too: once today's session has opened,
    the live quote's high is the authoritative high for today's trading day right
    through the evening, until the next session opens. That makes today the
    reference day for the whole day, covering the after-close window before the
    nightly job persists today's bar.
    """
    if now_et.weekday() >= 5:  # Sat/Sun
        return False
    return (now_et.hour, now_et.minute) >= _MARKET_OPEN


def _today_bar_is_final(now_et: datetime) -> bool:
    """Today's daily bar is only final once the regular session has closed."""
    if now_et.weekday() >= 5:
        return False
    return (now_et.hour, now_et.minute) >= _MARKET_CLOSE


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ATHResult:
    is_ath: bool                # did the reference trading day reach a new ATH?
    ath_price: float            # all-time high price to display
    ath_date: date              # date of that high
    days_since_ath: int


@dataclass
class PastValuesResult:
    values: list[float]         # up to 15 most recent trading days, oldest → newest
    avg: float
    count: int                  # actual days available (may be < 15 for new listings)


@dataclass
class YearHighResult:
    high_price: float
    high_date: date


# ---------------------------------------------------------------------------
# Seeding / updating
# ---------------------------------------------------------------------------

async def seed_symbol(symbol: str) -> int:
    """
    Fetch full price history from yfinance and upsert into daily_prices.
    Returns number of rows inserted/updated.
    Safe to call multiple times (upserts).
    """
    df = await asyncio.to_thread(_fetch_yfinance, symbol, period="max")
    if df is None or df.empty:
        return 0
    return await _upsert_dataframe(symbol, df)


async def update_symbol_yesterday(symbol: str) -> int:
    """Append the most recent ~5 days (idempotent, handles weekends)."""
    df = await asyncio.to_thread(_fetch_yfinance, symbol, period="5d")
    if df is None or df.empty:
        return 0
    return await _upsert_dataframe(symbol, df)


async def update_all_known_symbols() -> None:
    """Nightly job: update yesterday's bar for all symbols we have history for."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT DISTINCT symbol FROM daily_prices")
        )
        symbols = [row[0] for row in result.fetchall()]

    for symbol in symbols:
        try:
            await update_symbol_yesterday(symbol)
        except Exception:
            pass  # log in production; don't let one failure block others
        await asyncio.sleep(0.5)  # respect yfinance rate limits


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def ensure_seeded(symbol: str) -> None:
    """Seed symbol if it has no history yet."""
    async with async_session() as session:
        result = await session.execute(
            select(DailyPrice).where(DailyPrice.symbol == symbol).limit(1)
        )
        if result.scalar_one_or_none() is None:
            await seed_symbol(symbol)


async def _max_high_before(session, symbol: str, before: date) -> tuple[float, date] | None:
    """Highest daily high (and its date) strictly before `before`."""
    result = await session.execute(
        text("""
            SELECT high, date
            FROM daily_prices
            WHERE symbol = :symbol AND high IS NOT NULL AND date < :before
            ORDER BY high DESC
            LIMIT 1
        """),
        {"symbol": symbol, "before": before},
    )
    row = result.fetchone()
    return (float(row[0]), row[1]) if row else None


async def get_ath_status(
    symbol: str,
    today_high: float,
    now_et: datetime | None = None,
) -> ATHResult | None:
    """
    Decide ATH status against a *reference trading day*:

      - During a live regular session (and right after close, before the bar is
        persisted) the reference day is today, using the live intraday high.
      - Outside trading hours / weekends / holidays the reference day is the most
        recent completed trading day stored in the DB.

    The reference day's high is compared against the highest high of all strictly
    earlier days. A new high (>=) on the reference day flags is_ath=True.
    """
    now_et = now_et or _now_et()
    today = now_et.date()
    live = _session_started(now_et) and today_high and today_high > 0

    async with async_session() as session:
        if live:
            ref_high, ref_date = float(today_high), today
        else:
            result = await session.execute(
                text("""
                    SELECT high, date
                    FROM daily_prices
                    WHERE symbol = :symbol AND high IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 1
                """),
                {"symbol": symbol},
            )
            row = result.fetchone()
            if row is None:
                return None
            ref_high, ref_date = float(row[0]), row[1]

        prior = await _max_high_before(session, symbol, ref_date)

    prior_high = prior[0] if prior else 0.0
    is_ath = ref_high > 0 and ref_high >= prior_high

    if is_ath:
        return ATHResult(
            is_ath=True,
            ath_price=ref_high,
            ath_date=ref_date,
            days_since_ath=(today - ref_date).days,
        )

    # Not a new high → the all-time high is the earlier peak.
    prior_high, prior_date = prior
    return ATHResult(
        is_ath=False,
        ath_price=prior_high,
        ath_date=prior_date,
        days_since_ath=(today - prior_date).days,
    )


async def get_past_values(symbol: str, days: int = 15) -> PastValuesResult:
    """Return past N trading days' trading values, ordered oldest → newest."""
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT trading_value
                FROM daily_prices
                WHERE symbol = :symbol AND trading_value IS NOT NULL
                ORDER BY date DESC
                LIMIT :days
            """),
            {"symbol": symbol, "days": days},
        )
        rows = result.fetchall()

    # Reverse so values go oldest → newest (left → right on chart)
    values = [float(r[0]) for r in reversed(rows)]
    avg = sum(values) / len(values) if values else 0.0
    return PastValuesResult(values=values, avg=avg, count=len(values))


async def get_year_high(symbol: str) -> YearHighResult | None:
    """Return the 52-week (1-year) high price and date."""
    one_year_ago = date.today() - timedelta(days=365)
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT high, date
                FROM daily_prices
                WHERE symbol = :symbol
                  AND high IS NOT NULL
                  AND date >= :one_year_ago
                ORDER BY high DESC
                LIMIT 1
            """),
            {"symbol": symbol, "one_year_ago": one_year_ago},
        )
        row = result.fetchone()
        if row is None:
            return None
        return YearHighResult(high_price=float(row[0]), high_date=row[1])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol: str, period: str) -> pd.DataFrame | None:
    """Synchronous yfinance fetch (run in thread pool)."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=True)
        return df if not df.empty else None
    except Exception:
        return None


async def _upsert_dataframe(symbol: str, df: pd.DataFrame) -> int:
    """Insert or update rows from a yfinance DataFrame.

    Today's in-progress bar is skipped until the regular session closes, so the
    stored history only ever contains *completed* trading days. This keeps the
    ATH baseline clean (no partial-day contamination, no double-counting against
    the live quote).
    """
    now_et = _now_et()
    today = now_et.date()
    keep_today = _today_bar_is_final(now_et)

    rows = []
    for idx, row in df.iterrows():
        price_date = idx.date() if hasattr(idx, "date") else idx
        if price_date == today and not keep_today:
            continue
        close = float(row["Close"]) if pd.notna(row.get("Close")) else None
        volume = int(row["Volume"]) if pd.notna(row.get("Volume")) else None
        trading_value = round(close * volume, 4) if close and volume else None
        rows.append({
            "symbol": symbol,
            "date": price_date,
            "open": float(row["Open"]) if pd.notna(row.get("Open")) else None,
            "high": float(row["High"]) if pd.notna(row.get("High")) else None,
            "low": float(row["Low"]) if pd.notna(row.get("Low")) else None,
            "close": close,
            "volume": volume,
            "trading_value": trading_value,
        })

    if not rows:
        return 0

    async with async_session() as session:
        await session.execute(
            text("""
                INSERT INTO daily_prices
                    (symbol, date, open, high, low, close, volume, trading_value)
                VALUES
                    (:symbol, :date, :open, :high, :low, :close, :volume, :trading_value)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open          = EXCLUDED.open,
                    high          = EXCLUDED.high,
                    low           = EXCLUDED.low,
                    close         = EXCLUDED.close,
                    volume        = EXCLUDED.volume,
                    trading_value = EXCLUDED.trading_value
            """),
            rows,
        )
        await session.commit()

    return len(rows)

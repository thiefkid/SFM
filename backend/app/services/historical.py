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
from sqlalchemy import text

from app.core.database import async_session


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


def _last_expected_session(now_et: datetime) -> date:
    """
    The most recent date for which a *completed* daily bar should exist
    (holiday-naive — holidays just cause a harmless re-fetch that finds nothing).

    Today counts only once its regular session has closed; otherwise we step
    back to the previous weekday.
    """
    d = now_et.date()
    if now_et.weekday() < 5 and (now_et.hour, now_et.minute) >= _MARKET_CLOSE:
        return d
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


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
    dates: list[date]           # trading date for each value (parallel to `values`)


@dataclass
class YearHighResult:
    high_price: float
    high_date: date


# ---------------------------------------------------------------------------
# Seeding / updating
# ---------------------------------------------------------------------------

async def seed_symbol(symbol: str) -> int:
    """
    Fetch the full price history from yfinance and upsert into daily_prices.
    Overwrites overlapping rows (ON CONFLICT DO UPDATE), so it both backfills
    any gaps and normalises older rows to the current adjustment basis.
    Returns number of rows inserted/updated.
    """
    df = await asyncio.to_thread(_fetch_yfinance, symbol, period="max")
    if df is None or df.empty:
        return 0
    return await _upsert_dataframe(symbol, df)


async def update_all_known_symbols() -> None:
    """Nightly job (best-effort): refresh every symbol we have history for.

    Cloud Run scales to zero, so this scheduler is not guaranteed to fire —
    ensure_fresh on each /refresh is the real source of truth. This is just a
    bonus top-up when the container happens to be alive.
    """
    async with async_session() as session:
        result = await session.execute(
            text("SELECT DISTINCT symbol FROM daily_prices")
        )
        symbols = [row[0] for row in result.fetchall()]

    for symbol in symbols:
        try:
            await ensure_fresh(symbol)
        except Exception:
            pass  # log in production; don't let one failure block others
        await asyncio.sleep(0.5)  # respect yfinance rate limits


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def _latest_stored_date(symbol: str) -> date | None:
    """Most recent date we have a bar for, or None if the symbol is unseeded."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT MAX(date) FROM daily_prices WHERE symbol = :symbol"),
            {"symbol": symbol},
        )
        row = result.fetchone()
        return row[0] if row and row[0] else None


async def ensure_fresh(symbol: str, now_et: datetime | None = None) -> None:
    """
    Guarantee complete, up-to-date history for a symbol before indicators run.

    Because Cloud Run scales to zero the nightly scheduler can't be relied on,
    so freshness is enforced here on every refresh. If we're already holding the
    most recent completed session we do nothing (no network call); otherwise we
    re-pull the full history. A full re-pull (rather than a 5-day patch) is
    intentional: it backfills arbitrarily long gaps for symbols that dropped out
    of the top-10 for a while, and overwrites any stale rows — so ATH and the
    52-week high are always computed over the complete, correctly-adjusted series.
    """
    now_et = now_et or _now_et()
    latest = await _latest_stored_date(symbol)
    if latest is not None and latest >= _last_expected_session(now_et):
        return
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

    # Safety guard (trading-critical): in a live session the reference high comes
    # from the live quote, not the DB. If there is *no* prior stored history we
    # cannot validate an all-time high — this happens only when seeding failed
    # (yfinance returned nothing) or for a same-day IPO. Declaring "ATH TODAY"
    # off a live price with a zero baseline is a false positive that could drive
    # a bad trade, so surface "unknown" (None → N/A in the UI) instead.
    if live and prior is None:
        return None

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
    """Return past N trading days' trading values + dates, ordered oldest → newest."""
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT trading_value, date
                FROM daily_prices
                WHERE symbol = :symbol AND trading_value IS NOT NULL
                ORDER BY date DESC
                LIMIT :days
            """),
            {"symbol": symbol, "days": days},
        )
        rows = list(reversed(result.fetchall()))  # oldest → newest (left → right)

    values = [float(r[0]) for r in rows]
    dates = [r[1] for r in rows]
    avg = sum(values) / len(values) if values else 0.0
    return PastValuesResult(values=values, avg=avg, count=len(values), dates=dates)


async def get_year_high(
    symbol: str,
    today_high: float,
    now_et: datetime | None = None,
) -> YearHighResult | None:
    """
    Highest high over the trailing 52 weeks, including today's live intraday high.

    Mirrors get_ath_status: during/after a session today's live high is folded in
    (today's bar isn't persisted intraday), otherwise the most recent completed
    day already sits in the stored window.
    """
    now_et = now_et or _now_et()
    today = now_et.date()
    one_year_ago = today - timedelta(days=365)
    live = _session_started(now_et) and today_high and today_high > 0

    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT high, date
                FROM daily_prices
                WHERE symbol = :symbol
                  AND high IS NOT NULL
                  AND date >= :one_year_ago
                  AND date < :today
                ORDER BY high DESC
                LIMIT 1
            """),
            {"symbol": symbol, "one_year_ago": one_year_ago, "today": today},
        )
        row = result.fetchone()

    candidates: list[tuple[float, date]] = []
    if row is not None:
        candidates.append((float(row[0]), row[1]))
    if live:
        candidates.append((float(today_high), today))

    if not candidates:
        return None
    high, high_date = max(candidates, key=lambda c: c[0])
    return YearHighResult(high_price=high, high_date=high_date)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol: str, period: str) -> pd.DataFrame | None:
    """Synchronous yfinance fetch (run in thread pool).

    auto_adjust=False is deliberate and matters for ATH/52-week accuracy:
    Yahoo's OHLC are split-adjusted but NOT dividend-adjusted, which is exactly
    the basis the live Finnhub quote uses. With auto_adjust=True the historical
    High column gets back-adjusted *down* for dividends, so it sits below the
    prices actually traded — comparing that against an unadjusted live price
    produces false all-time highs. Splits are still adjusted (by Yahoo), so a
    pre-split peak won't spuriously beat the current price.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=False)
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

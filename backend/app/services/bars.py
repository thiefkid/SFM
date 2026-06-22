"""
On-demand intraday 1-minute price bars per symbol via yfinance.

Fetched only when a user taps the I1 (price vs open) indicator to see today's
intraday price path. yfinance is the only free source with intraday bars:
Polygon's free tier is EOD-only and Finnhub's free tier has no candle endpoint.

Results are cached for 90s — 1-minute bars update slowly and the forming
(current) bar is partial anyway, so there's no value in re-fetching faster.
"""

import asyncio
import logging
import time
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_CACHE_TTL = 90  # seconds
# symbol -> (fetched_at_monotonic, list[bar dict])
_cache: dict[str, tuple[float, list[dict]]] = {}


def _fetch_intraday(symbol: str) -> list[dict]:
    """Blocking yfinance call → today's 1-minute close bars. Runs in a thread.

    Each bar: {"t": ISO-8601 ET timestamp, "close": float}. When the market is
    closed yfinance returns the most recent trading day's bars, which is exactly
    what we want to display.
    """
    df = yf.Ticker(symbol).history(period="1d", interval="1m", auto_adjust=False)
    if df is None or df.empty:
        return []

    bars: list[dict] = []
    for ts, row in df.iterrows():
        close = row.get("Close")
        # Skip gaps/halted minutes — a NaN close would break JSON and the chart.
        if close is None or pd.isna(close):
            continue
        dt = ts.to_pydatetime()
        # yfinance intraday timestamps are tz-aware; normalise to ET so the
        # frontend time labels are exact and never guessed.
        if dt.tzinfo is not None:
            dt = dt.astimezone(_ET)
        bars.append({"t": dt.isoformat(), "close": float(close)})
    return bars


async def get_intraday_bars(symbol: str) -> list[dict]:
    """Return today's 1-minute close bars for a symbol.

    Each item: {"t": ISO-8601 ET timestamp, "close": float}, oldest → newest.
    Returns an empty list on any failure or when no data is available (thin
    ticker, pre-open, mock mode).
    """
    if settings.scraper_mock_mode:
        return []

    now = time.monotonic()
    cached = _cache.get(symbol)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        bars = await asyncio.to_thread(_fetch_intraday, symbol)
    except Exception as exc:
        logger.warning("Intraday bars failed for %s: %s", symbol, exc)
        return []

    _cache[symbol] = (now, bars)
    logger.info("Intraday %s: fetched %d bars", symbol, len(bars))
    return bars

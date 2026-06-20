"""
Live quote service.

Replaces per-stock and NASDAQ scraping with:
  - Finnhub /quote  → price, open, high, low, prev_close (realtime US stocks)
  - yfinance batch  → today's volume (for turnover) and NASDAQ Composite

Futu ranking scrape (top 10) remains in futu_scraper — Finnhub doesn't offer
a most-active endpoint on the free tier, and the user requires Futu's
turnover-based ranking specifically.
"""

import asyncio
import logging
from datetime import date
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import yfinance as yf

from app.core.config import settings
from app.services.futu_scraper import (
    NasdaqSnapshot,
    StockSnapshot,
    _MOCK_NASDAQ,
    _MOCK_STOCKS,
    _make_fallback_snapshot,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"

# Reuse connection pool across all refreshes
_http_client = httpx.AsyncClient(timeout=10.0)


async def _finnhub_quote(symbol: str) -> dict:
    r = await _http_client.get(
        _FINNHUB_QUOTE,
        params={"symbol": symbol, "token": settings.finnhub_api_key},
    )
    r.raise_for_status()
    return r.json()


def _yf_volumes(symbols: list[str]) -> dict[str, float]:
    """Single yfinance download for all symbols' current-day volume.

    Feeds only I4's today turnover (price × volume). NASDAQ is fetched
    separately in get_nasdaq_snapshot (fast_info) — bundling the index here just
    pulled ^IXIC twice and discarded the result, so it's intentionally omitted.
    """
    if not symbols:
        return {}
    try:
        df = yf.download(symbols, period="2d", progress=False, auto_adjust=True, threads=True)
    except Exception as exc:
        logger.warning("yfinance volume download failed: %s", exc)
        return {s: 0.0 for s in symbols}

    if df.empty:
        return {s: 0.0 for s in symbols}

    # Volume per symbol from the most recent row. With multiple symbols df["Volume"]
    # is a DataFrame (columns = symbols) and .iloc[-1] is a Series; with a single
    # symbol it's a plain Series and .iloc[-1] is a scalar. Guard NaN so a halted
    # ticker can't poison today_value with NaN (which breaks JSON serialisation).
    try:
        last = df["Volume"].iloc[-1]
        volumes: dict[str, float] = {}
        for s in symbols:
            raw = last.get(s) if isinstance(last, pd.Series) else last
            volumes[s] = float(raw) if raw is not None and pd.notna(raw) else 0.0
        return volumes
    except Exception as exc:
        logger.warning("yfinance volume parse failed: %s", exc)
        return {s: 0.0 for s in symbols}




def _build_snapshot(symbol: str, quote: dict, volume: float) -> StockSnapshot:
    if not quote.get("c"):
        return _make_fallback_snapshot(symbol, "Finnhub returned empty quote")
    price = float(quote["c"])
    raw_high = float(quote.get("h") or 0.0)
    raw_low = float(quote.get("l") or 0.0)
    # Finnhub's high/low can lag the last price (notably on thin/recent tickers),
    # which would make I3 = (price-open)/(high-open) exceed 1.0 and corrupt ATH.
    # The day's high can never be below the last print, nor the low above it, so
    # clamp the candle to stay valid: low <= price <= high.
    return StockSnapshot(
        symbol=symbol,
        rt_price=price,
        open_price=float(quote.get("o") or 0.0),
        prev_close=float(quote.get("pc") or 0.0),
        today_high=max(raw_high, price),
        today_low=min(raw_low, price) if raw_low > 0 else price,
        today_value=price * volume,
    )


async def get_all_snapshots(symbols: list[str]) -> list[StockSnapshot]:
    """Fetch quotes for all symbols in parallel via Finnhub + yfinance volume."""
    if settings.scraper_mock_mode:
        return [_MOCK_STOCKS.get(s, _make_fallback_snapshot(s)) for s in symbols]

    if not settings.finnhub_api_key:
        return [_make_fallback_snapshot(s, "FINNHUB_API_KEY not configured") for s in symbols]

    quotes, volumes = await asyncio.gather(
        asyncio.gather(*[_finnhub_quote(s) for s in symbols]),
        asyncio.to_thread(_yf_volumes, symbols),
    )

    results = []
    for symbol, quote in zip(symbols, quotes):
        try:
            results.append(_build_snapshot(symbol, quote, volumes.get(symbol, 0.0)))
        except Exception as exc:
            results.append(_make_fallback_snapshot(symbol, str(exc)))
    return results


async def get_nasdaq_snapshot() -> NasdaqSnapshot:
    """NASDAQ Composite via yfinance (^IXIC). Finnhub indices are paid-tier only."""
    if settings.scraper_mock_mode:
        return _MOCK_NASDAQ

    def _fetch() -> NasdaqSnapshot:
        try:
            info = yf.Ticker("^IXIC").fast_info
            return NasdaqSnapshot(
                rt_level=float(info.get("last_price") or 0.0),
                open_level=float(info.get("open") or 0.0),
                prev_close=float(info.get("previous_close") or 0.0),
            )
        except Exception as exc:
            return NasdaqSnapshot(rt_level=0.0, open_level=0.0, prev_close=0.0, error=str(exc))

    return await asyncio.to_thread(_fetch)

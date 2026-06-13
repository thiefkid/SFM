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


def _yf_batch(symbols: list[str]) -> tuple[dict[str, float], NasdaqSnapshot]:
    """Single yfinance download for all symbol volumes + NASDAQ in one HTTP call."""
    all_syms = [*symbols, "^IXIC"]
    try:
        df = yf.download(all_syms, period="2d", progress=False, auto_adjust=True, threads=True)
    except Exception as exc:
        logger.warning("yfinance batch download failed: %s", exc)
        return {s: 0.0 for s in symbols}, NasdaqSnapshot(rt_level=0.0, open_level=0.0, prev_close=0.0, error=str(exc))

    # Volume per symbol (today's last row)
    volumes: dict[str, float] = {}
    try:
        vol = df["Volume"]
        last = vol.iloc[-1] if not df.empty else pd.Series(dtype=float)
        for s in symbols:
            volumes[s] = float(last[s] if isinstance(last, pd.Series) and s in last else 0 or 0)
    except Exception:
        volumes = {s: 0.0 for s in symbols}

    # NASDAQ: rt from last close, open from today, prev_close from yesterday
    nasdaq = NasdaqSnapshot(rt_level=0.0, open_level=0.0, prev_close=0.0)
    try:
        closes = df["Close"]["^IXIC"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
        opens = df["Open"]["^IXIC"] if isinstance(df.columns, pd.MultiIndex) else df["Open"]
        if len(closes) >= 2:
            nasdaq = NasdaqSnapshot(
                rt_level=float(closes.iloc[-1] or 0),
                open_level=float(opens.iloc[-1] or 0),
                prev_close=float(closes.iloc[-2] or 0),
            )
        elif len(closes) == 1:
            nasdaq = NasdaqSnapshot(
                rt_level=float(closes.iloc[-1] or 0),
                open_level=float(opens.iloc[-1] or 0),
                prev_close=0.0,
            )
    except Exception as exc:
        logger.warning("yfinance NASDAQ parse failed: %s", exc)

    return volumes, nasdaq


def _build_snapshot(symbol: str, quote: dict, volume: float) -> StockSnapshot:
    if not quote.get("c"):
        return _make_fallback_snapshot(symbol, "Finnhub returned empty quote")
    price = float(quote["c"])
    return StockSnapshot(
        symbol=symbol,
        rt_price=price,
        open_price=float(quote.get("o") or 0.0),
        prev_close=float(quote.get("pc") or 0.0),
        today_high=float(quote.get("h") or 0.0),
        today_low=float(quote.get("l") or 0.0),
        today_value=price * volume,
    )


async def get_all_snapshots(symbols: list[str]) -> list[StockSnapshot]:
    """Fetch quotes for all symbols in parallel via Finnhub + yfinance volume."""
    if settings.scraper_mock_mode:
        return [_MOCK_STOCKS.get(s, _make_fallback_snapshot(s)) for s in symbols]

    if not settings.finnhub_api_key:
        return [_make_fallback_snapshot(s, "FINNHUB_API_KEY not configured") for s in symbols]

    quotes, (volumes, _nasdaq) = await asyncio.gather(
        asyncio.gather(*[_finnhub_quote(s) for s in symbols]),
        asyncio.to_thread(_yf_batch, symbols),
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

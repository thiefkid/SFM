"""
Live quote service.

Replaces per-stock and NASDAQ scraping with:
  - Finnhub /quote      → price, open, high, low, prev_close (realtime US stocks)
  - yfinance fast_info  → today's volume (for turnover) and NASDAQ index

Futu ranking scrape (top 10) remains in futu_scraper — Finnhub doesn't offer
a most-active endpoint on the free tier, and the user requires Futu's
turnover-based ranking specifically.
"""

import asyncio
import logging

import httpx
import yfinance as yf

from app.core.config import settings
from app.services.futu_scraper import NasdaqSnapshot, StockSnapshot

logger = logging.getLogger(__name__)

_FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"


async def _finnhub_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    r = await client.get(
        _FINNHUB_QUOTE,
        params={"symbol": symbol, "token": settings.finnhub_api_key},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def _yf_volume(symbol: str) -> float:
    """Today's traded volume (shares). Synchronous yfinance call."""
    try:
        info = yf.Ticker(symbol).fast_info
        return float(info.get("last_volume") or info.get("regular_market_volume") or 0)
    except Exception as exc:
        logger.warning("yfinance volume lookup failed for %s: %s", symbol, exc)
        return 0.0


async def _get_one(client: httpx.AsyncClient, symbol: str) -> StockSnapshot:
    try:
        quote, volume = await asyncio.gather(
            _finnhub_quote(client, symbol),
            asyncio.to_thread(_yf_volume, symbol),
        )
        # Finnhub returns zeros when symbol is unknown or market closed and no quote.
        if not quote.get("c"):
            return StockSnapshot(
                symbol=symbol,
                rt_price=0.0, open_price=0.0, prev_close=0.0,
                today_high=0.0, today_low=0.0, today_value=0.0,
                error="Finnhub returned empty quote",
            )
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
    except Exception as exc:
        return StockSnapshot(
            symbol=symbol,
            rt_price=0.0, open_price=0.0, prev_close=0.0,
            today_high=0.0, today_low=0.0, today_value=0.0,
            error=str(exc),
        )


async def get_all_snapshots(symbols: list[str]) -> list[StockSnapshot]:
    """Fetch quotes for all symbols in parallel via Finnhub + yfinance volume."""
    if not settings.finnhub_api_key:
        return [
            StockSnapshot(
                symbol=s,
                rt_price=0.0, open_price=0.0, prev_close=0.0,
                today_high=0.0, today_low=0.0, today_value=0.0,
                error="FINNHUB_API_KEY not configured",
            )
            for s in symbols
        ]

    async with httpx.AsyncClient() as client:
        return list(await asyncio.gather(*[_get_one(client, s) for s in symbols]))


async def get_nasdaq_snapshot() -> NasdaqSnapshot:
    """NASDAQ Composite via yfinance (^IXIC). Finnhub indices are paid-tier only."""
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

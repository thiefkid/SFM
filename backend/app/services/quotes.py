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


def _yf_intraday_turnover(
    symbols: list[str],
    interval: str = "15m",
    period: str = "60d",
) -> dict[str, dict[date, float]]:
    """Bar-aggregated turnover per symbol per trading day.

    For each intraday bar: typical price (H+L+C)/3 × bar volume, summed by ET
    trading date. This Σ(price×volume) is a true turnover estimate — far closer
    to exchange-reported turnover than daily close×volume, which over/under-states
    on volatile days. 15m/60d covers I4's 15-day window in one batched download.

    Returns {} on any failure so callers fall back to the close×volume basis.
    """
    if not symbols:
        return {}
    try:
        df = yf.download(
            symbols, period=period, interval=interval,
            auto_adjust=False, group_by="ticker", progress=False, threads=True,
        )
    except Exception as exc:
        logger.warning("yfinance intraday turnover download failed: %s", exc)
        return {}
    if df is None or df.empty:
        return {}

    out: dict[str, dict[date, float]] = {}
    for s in symbols:
        try:
            # group_by="ticker": columns are a MultiIndex (symbol, field) for
            # multiple symbols, but a plain Index for a single symbol.
            sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            sub = sub.dropna(subset=["Close", "Volume", "High", "Low"])
            if sub.empty:
                out[s] = {}
                continue
            typical = (sub["High"] + sub["Low"] + sub["Close"]) / 3.0
            bar_tv = typical * sub["Volume"]
            # Intraday index is tz-aware (exchange tz); normalise to ET dates.
            idx = sub.index
            local = idx.tz_convert(_ET) if idx.tz is not None else idx
            by_date: dict[date, float] = {}
            for d, v in zip((ts.date() for ts in local), bar_tv):
                if pd.notna(v):
                    by_date[d] = by_date.get(d, 0.0) + float(v)
            out[s] = by_date
        except Exception as exc:
            logger.warning("intraday turnover parse failed for %s: %s", s, exc)
            out[s] = {}
    return out


async def get_intraday_turnover(symbols: list[str]) -> dict[str, dict[date, float]]:
    """Async wrapper around the batched intraday turnover download."""
    if settings.scraper_mock_mode or not symbols:
        return {}
    return await asyncio.to_thread(_yf_intraday_turnover, symbols)


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

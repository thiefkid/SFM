"""
Company profile reference data per symbol via Finnhub /stock/profile2.

Primary use: market capitalisation. This is reference data that changes
rarely (shares outstanding + slow price drift), so it's fetched off the
critical refresh path and cached for a full day per process.

Finnhub returns marketCapitalization in millions of USD; we normalise to
absolute USD so the frontend can format consistently.
"""

import asyncio
import logging
from datetime import date, datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_PROFILE = "https://finnhub.io/api/v1/stock/profile2"
_http_client = httpx.AsyncClient(timeout=10.0)

# symbol -> (fetched_on_utc_date, market_cap_usd | None)
_cache: dict[str, tuple[date, float | None]] = {}


def _parse_market_cap(payload: dict) -> float | None:
    """Finnhub marketCapitalization is in millions USD → absolute USD."""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("marketCapitalization")
    try:
        mcap_millions = float(raw)
    except (TypeError, ValueError):
        return None
    if mcap_millions <= 0:
        return None
    return mcap_millions * 1_000_000


async def _fetch_market_cap(symbol: str) -> float | None:
    try:
        r = await _http_client.get(
            _FINNHUB_PROFILE,
            params={"symbol": symbol, "token": settings.finnhub_api_key},
        )
        r.raise_for_status()
        return _parse_market_cap(r.json())
    except Exception as exc:
        logger.warning("Finnhub profile failed for %s: %s", symbol, exc)
        return None


async def _resolve_one(symbol: str, today: date) -> tuple[str, float | None]:
    mcap: float | None = None
    try:
        if settings.finnhub_api_key:
            mcap = await _fetch_market_cap(symbol)
    except Exception as exc:
        logger.warning("Market cap resolution failed for %s: %s", symbol, exc)
    _cache[symbol] = (today, mcap)
    logger.info("Market cap %s: %s", symbol, mcap)
    return symbol, mcap


async def get_market_caps(symbols: list[str]) -> dict[str, float | None]:
    """Return {symbol: market_cap_usd|None}, cached once per UTC day."""
    if not symbols:
        return {}

    if settings.scraper_mock_mode:
        import hashlib
        return {
            s: float((int(hashlib.md5(s.encode()).hexdigest(), 16) % 900 + 1) * 1_000_000_000)
            for s in symbols
        }

    today = datetime.now(tz=timezone.utc).date()
    result: dict[str, float | None] = {}
    to_fetch: list[str] = []
    for s in symbols:
        cached = _cache.get(s)
        if cached and cached[0] == today:
            result[s] = cached[1]
        else:
            to_fetch.append(s)

    if to_fetch:
        resolved = await asyncio.gather(
            *[_resolve_one(s, today) for s in to_fetch],
            return_exceptions=True,
        )
        for item in resolved:
            if isinstance(item, Exception):
                logger.warning("Market cap resolution failed: %s", item)
                continue
            s, mcap = item
            result[s] = mcap

    return result

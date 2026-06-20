"""
Polygon.io daily aggregates — authoritative trading turnover.

Turnover = v × vw, where vw is the volume-weighted average price computed by
Polygon from every trade on the consolidated tape. This is dramatically more
accurate than close×volume (yfinance) or bar-aggregated VWAP from 15m bars.

Free tier: 5 requests/minute, 15-min delayed quotes, full historical daily data.
We cache aggressively (settled daily bars never change) so API calls happen only
once per process lifecycle — well within the rate limit.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_POLYGON_AGGS = "https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"

_http_client = httpx.AsyncClient(timeout=15.0)

# Cache: (symbol, date) → turnover.  Settled daily bars never change, so this
# cache is valid for the entire process lifetime.  Only "today" gets re-fetched
# because it accumulates through the trading day.
_cache: dict[tuple[str, date], float] = {}
_cache_populated_symbols: set[str] = set()


async def _fetch_daily_aggs(symbol: str, from_date: str, to_date: str) -> list[dict]:
    url = _POLYGON_AGGS.format(symbol=symbol, from_date=from_date, to_date=to_date)
    for attempt in range(4):
        try:
            r = await _http_client.get(
                url,
                params={"adjusted": "true", "sort": "asc", "apiKey": settings.polygon_api_key},
            )
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.info("Polygon 429 for %s, backing off %ds", symbol, wait)
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            return data.get("results") or []
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            logger.warning("Polygon fetch failed for %s (attempt %d): %s", symbol, attempt + 1, exc)
            if attempt < 3:
                await asyncio.sleep(2 * (attempt + 1))
    return []


def _ts_to_date(t_ms: int) -> date:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).date()


async def _fetch_and_cache(symbol: str, from_date: str, to_date: str) -> dict[date, float]:
    bars = await _fetch_daily_aggs(symbol, from_date, to_date)
    result: dict[date, float] = {}
    for bar in bars:
        v = bar.get("v")
        vw = bar.get("vw")
        t = bar.get("t")
        if v and vw and t:
            d = _ts_to_date(t)
            turnover = float(v) * float(vw)
            _cache[(symbol, d)] = turnover
            result[d] = turnover
    _cache_populated_symbols.add(symbol)
    return result


async def get_daily_turnover(
    symbols: list[str],
    days: int = 20,
) -> dict[str, dict[date, float]]:
    """Fetch authoritative daily turnover (v × vw) for all symbols.

    Cached per process — settled bars never change. Only uncached symbols hit
    the API. Returns {symbol: {date: turnover_dollars}} or {} on failure.
    """
    if not symbols or not settings.polygon_api_key:
        return {}

    today = date.today()
    from_date = (today - timedelta(days=days + 10)).isoformat()
    to_date = today.isoformat()

    # Determine which symbols need fetching (not yet cached this process)
    need_fetch = [s for s in symbols if s not in _cache_populated_symbols]

    if need_fetch:
        # Fetch in batches of 5 to respect 5 req/min rate limit.
        # First batch fires immediately; subsequent batches wait 62s.
        for batch_idx in range(0, len(need_fetch), 5):
            batch = need_fetch[batch_idx : batch_idx + 5]
            if batch_idx > 0:
                logger.info("Polygon rate limit: waiting 62s before batch %d", batch_idx // 5 + 1)
                await asyncio.sleep(62)
            await asyncio.gather(*[_fetch_and_cache(s, from_date, to_date) for s in batch])

    # Build result from cache
    out: dict[str, dict[date, float]] = {}
    for s in symbols:
        turnover_by_date: dict[date, float] = {}
        for d_offset in range(days + 10):
            d = today - timedelta(days=d_offset)
            key = (s, d)
            if key in _cache:
                turnover_by_date[d] = _cache[key]
        out[s] = turnover_by_date
    return out

"""
Polygon.io daily aggregates — authoritative trading turnover.

Turnover = v × vw, where vw is the volume-weighted average price computed by
Polygon from every trade on the consolidated tape. This is dramatically more
accurate than close×volume (yfinance) or bar-aggregated VWAP from 15m bars.

Free tier: 5 requests/minute, END-OF-DAY only (no intraday), 2 years history.
We cache aggressively (settled daily bars never change) so API calls happen only
once per process lifecycle — well within the rate limit.
Today's live turnover comes from Finnhub/yfinance, not Polygon.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_POLYGON_AGGS = "https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
_POLYGON_OPEN_CLOSE = "https://api.polygon.io/v1/open-close/{symbol}/{date}"

_http_client = httpx.AsyncClient(timeout=15.0)

# Cache: (symbol, date) → turnover.  Settled daily bars never change, so this
# cache is valid for the entire process lifetime.  Only "today" gets re-fetched
# because it accumulates through the trading day.
_cache: dict[tuple[str, date], float] = {}
_cache_populated_symbols: set[str] = set()


@dataclass
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    vw: float
    turnover: float


_bar_cache: dict[tuple[str, date], DailyBar] = {}


@dataclass
class OfficialOHLC:
    """Official regular-session OHLC from Polygon's /v1/open-close endpoint.

    Unlike the /v2/aggs daily bar (whose open/close include pre- and post-market
    trades), these are the authoritative regular-session opening and closing
    auction prices — exactly what I1/I2/I3 should reference after the close.
    """
    date: date
    open: float
    high: float
    low: float
    close: float


# Settled daily open/close never changes → cache for the whole process lifetime.
_open_close_cache: dict[tuple[str, date], OfficialOHLC] = {}


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
            results = data.get("results") or []
            logger.info("Polygon API %s: HTTP %d, %d results, status=%s",
                        symbol, r.status_code, len(results), data.get("status"))
            return results
        except httpx.HTTPStatusError as exc:
            logger.error("Polygon API HTTP error for %s: %d %s",
                         symbol, exc.response.status_code, exc.response.text[:200])
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
    if not bars:
        logger.warning("Polygon returned 0 bars for %s (%s → %s)", symbol, from_date, to_date)
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
            _bar_cache[(symbol, d)] = DailyBar(
                date=d,
                open=float(bar.get("o", 0)),
                high=float(bar.get("h", 0)),
                low=float(bar.get("l", 0)),
                close=float(bar.get("c", 0)),
                volume=float(v),
                vw=float(vw),
                turnover=turnover,
            )
    logger.info("Polygon %s: %d bars → %d turnover days (range %s to %s)",
                symbol, len(bars), len(result), from_date, to_date)
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
    if not symbols:
        return {}
    if not settings.polygon_api_key:
        logger.warning("POLYGON_API_KEY not set — falling back to DB close×volume turnover")
        return {}

    today = date.today()
    from_date = (today - timedelta(days=days + 10)).isoformat()
    to_date = today.isoformat()

    # Determine which symbols need fetching (not yet cached this process)
    need_fetch = [s for s in symbols if s not in _cache_populated_symbols]

    if need_fetch:
        logger.info("Polygon: fetching %d symbols: %s", len(need_fetch), need_fetch)
        for batch_idx in range(0, len(need_fetch), 5):
            batch = need_fetch[batch_idx : batch_idx + 5]
            if batch_idx > 0:
                logger.info("Polygon rate limit: waiting 62s before batch %d", batch_idx // 5 + 1)
                await asyncio.sleep(62)
            await asyncio.gather(*[_fetch_and_cache(s, from_date, to_date) for s in batch])
    else:
        logger.info("Polygon: all %d symbols cached, no API calls needed", len(symbols))

    # Build result from cache
    out: dict[str, dict[date, float]] = {}
    logger.info("Polygon bar cache: %d entries total", len(_bar_cache))
    for s in symbols:
        turnover_by_date: dict[date, float] = {}
        for d_offset in range(days + 10):
            d = today - timedelta(days=d_offset)
            key = (s, d)
            if key in _cache:
                turnover_by_date[d] = _cache[key]
        out[s] = turnover_by_date
        logger.info("Polygon turnover for %s: %d days cached, sample: %s",
                     s, len(turnover_by_date),
                     {d.isoformat(): f"${v:,.0f}" for d, v in sorted(turnover_by_date.items())[-3:]})
    return out


def get_cached_bar(symbol: str, bar_date: date) -> DailyBar | None:
    """Return cached Polygon daily bar for a specific symbol/date, or None."""
    return _bar_cache.get((symbol, bar_date))


async def get_official_ohlc(symbol: str, day: date) -> OfficialOHLC | None:
    """Authoritative regular-session OHLC for a settled trading day.

    Uses Polygon's /v1/open-close, whose `open`/`close` are the official
    opening and closing auction prices (pre-/post-market reported separately,
    not blended into the open like the daily aggregate bar).

    Returns None — so the caller falls back to Finnhub values — when:
      - no API key is configured;
      - the day hasn't settled yet (HTTP 404 / status != "OK"); or
      - any network/parse error occurs.

    Results are cached per process: a settled day's official OHLC never changes,
    and a not-yet-settled day is intentionally NOT cached so it is retried.
    """
    if not settings.polygon_api_key:
        return None

    key = (symbol, day)
    cached = _open_close_cache.get(key)
    if cached is not None:
        return cached

    url = _POLYGON_OPEN_CLOSE.format(symbol=symbol, date=day.isoformat())
    for attempt in range(4):
        try:
            r = await _http_client.get(
                url,
                params={"adjusted": "true", "apiKey": settings.polygon_api_key},
            )
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.info("Polygon open-close 429 for %s, backing off %ds", symbol, wait)
                await asyncio.sleep(wait)
                continue
            # 404 = day not settled yet (normal right after the close). Not an
            # error — return None so the caller keeps Finnhub's values.
            if r.status_code == 404:
                logger.info("Polygon open-close %s %s: not settled yet (404)", symbol, day)
                return None
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("Polygon open-close failed for %s %s (attempt %d): %s",
                           symbol, day, attempt + 1, exc)
            if attempt < 3:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            return None

        if data.get("status") != "OK" or "open" not in data or "close" not in data:
            logger.info("Polygon open-close %s %s: status=%s, not usable",
                        symbol, day, data.get("status"))
            return None

        ohlc = OfficialOHLC(
            date=day,
            open=float(data.get("open", 0.0)),
            high=float(data.get("high", 0.0)),
            low=float(data.get("low", 0.0)),
            close=float(data.get("close", 0.0)),
        )
        _open_close_cache[key] = ohlc
        logger.info("Polygon open-close %s %s: open=%.2f high=%.2f low=%.2f close=%.2f",
                    symbol, day, ohlc.open, ohlc.high, ohlc.low, ohlc.close)
        return ohlc

    return None

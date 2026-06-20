"""
Next earnings (results announcement) date per symbol.

Primary source : Finnhub /calendar/earnings  (confirmed/estimated upcoming).
Fallback       : yfinance Ticker.calendar     (Yahoo consensus).

Two free, independent sources — if Finnhub returns nothing (rate limit, tier
restriction, or no upcoming row) we fall back to Yahoo, so a single source
being wrong or empty can't blank the countdown.

Earnings dates are stable intraday, so each symbol is fetched at most once per
UTC day per process and cached.
"""

import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone

import httpx
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_EARNINGS = "https://finnhub.io/api/v1/calendar/earnings"
_http_client = httpx.AsyncClient(timeout=10.0)

# symbol -> (fetched_on_utc_date, next_earnings_date | None)
_cache: dict[str, tuple[date, date | None]] = {}


# ---------------------------------------------------------------------------
# Parsing (pure, unit-tested)
# ---------------------------------------------------------------------------

def _earliest_future(dates: list[date], today: date) -> date | None:
    future = [d for d in dates if d >= today]
    return min(future) if future else None


def _parse_finnhub(payload: dict, today: date) -> date | None:
    """Earliest upcoming date from a Finnhub /calendar/earnings response."""
    rows = (payload or {}).get("earningsCalendar") or []
    parsed: list[date] = []
    for r in rows:
        ds = r.get("date")
        if not ds:
            continue
        try:
            parsed.append(date.fromisoformat(ds))
        except (ValueError, TypeError):
            continue
    return _earliest_future(parsed, today)


def _parse_yf_calendar(cal, today: date) -> date | None:
    """Earliest upcoming date from a yfinance Ticker.calendar dict.

    `calendar` is a dict whose "Earnings Date" is a list of date/datetime
    (1 entry when confirmed, 2 when Yahoo only has an estimated range).
    """
    if not isinstance(cal, dict):
        return None
    raw = cal.get("Earnings Date")
    if not raw:
        return None
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    parsed: list[date] = []
    for d in raw:
        if isinstance(d, datetime):
            parsed.append(d.date())
        elif isinstance(d, date):
            parsed.append(d)
    return _earliest_future(parsed, today)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

async def _finnhub_next_earnings(symbol: str, today: date) -> date | None:
    to_date = today + timedelta(days=120)
    try:
        r = await _http_client.get(
            _FINNHUB_EARNINGS,
            params={
                "symbol": symbol,
                "from": today.isoformat(),
                "to": to_date.isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        r.raise_for_status()
        return _parse_finnhub(r.json(), today)
    except Exception as exc:
        logger.info("Finnhub earnings failed for %s: %s", symbol, exc)
        return None


def _yf_next_earnings(symbol: str, today: date) -> date | None:
    try:
        cal = yf.Ticker(symbol).calendar
    except Exception as exc:
        logger.info("yfinance earnings failed for %s: %s", symbol, exc)
        return None
    return _parse_yf_calendar(cal, today)


async def _resolve_one(symbol: str, today: date) -> tuple[str, date | None]:
    d: date | None = None
    source = "none"
    if settings.finnhub_api_key:
        d = await _finnhub_next_earnings(symbol, today)
        if d is not None:
            source = "finnhub"
    if d is None:
        d = await asyncio.to_thread(_yf_next_earnings, symbol, today)
        if d is not None:
            source = "yfinance"
    _cache[symbol] = (today, d)
    logger.info("Earnings %s: next=%s source=%s", symbol, d, source)
    return symbol, d


async def get_next_earnings(symbols: list[str]) -> dict[str, date | None]:
    """Return {symbol: next_earnings_date|None}, cached once per UTC day."""
    if not symbols:
        return {}

    if settings.scraper_mock_mode:
        base = date.today()
        return {
            s: base + timedelta(
                days=(int(hashlib.md5(s.encode()).hexdigest(), 16) % 60) + 1
            )
            for s in symbols
        }

    today = datetime.now(tz=timezone.utc).date()
    result: dict[str, date | None] = {}
    to_fetch: list[str] = []
    for s in symbols:
        cached = _cache.get(s)
        if cached and cached[0] == today:
            result[s] = cached[1]
        else:
            to_fetch.append(s)

    if to_fetch:
        resolved = await asyncio.gather(*[_resolve_one(s, today) for s in to_fetch])
        for s, d in resolved:
            result[s] = d

    return result

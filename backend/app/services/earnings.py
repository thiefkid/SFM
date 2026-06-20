"""
Upcoming corporate events per symbol: earnings date + dividend/ex-dividend dates.

Primary source : Finnhub /calendar/earnings  (earnings only).
Fallback/suppl.: yfinance Ticker.calendar     (earnings + dividends).

yfinance provides both earnings and dividend dates in a single calendar call,
so we always call it (as fallback for earnings if Finnhub misses, and as the
sole source for dividend dates). Both are stable intraday, cached per UTC day.
"""

import asyncio
import dataclasses
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone

import httpx
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_EARNINGS = "https://finnhub.io/api/v1/calendar/earnings"
_http_client = httpx.AsyncClient(timeout=10.0)


@dataclasses.dataclass(frozen=True, slots=True)
class UpcomingEvents:
    next_earnings: date | None = None
    next_dividend: date | None = None
    ex_dividend: date | None = None


# symbol -> (fetched_on_utc_date, UpcomingEvents)
_cache: dict[str, tuple[date, UpcomingEvents]] = {}


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


def _parse_yf_calendar(cal, today: date) -> UpcomingEvents:
    """Extract earnings + dividend dates from a yfinance Ticker.calendar dict."""
    if not isinstance(cal, dict):
        return UpcomingEvents()

    # Earnings
    earnings_raw = cal.get("Earnings Date")
    earnings: date | None = None
    if earnings_raw:
        if not isinstance(earnings_raw, (list, tuple)):
            earnings_raw = [earnings_raw]
        parsed: list[date] = []
        for d in earnings_raw:
            if isinstance(d, datetime):
                parsed.append(d.date())
            elif isinstance(d, date):
                parsed.append(d)
        earnings = _earliest_future(parsed, today)

    # Dividend Date (payment date)
    dividend = _parse_single_date(cal.get("Dividend Date"), today)
    # Ex-Dividend Date
    ex_div = _parse_single_date(cal.get("Ex-Dividend Date"), today)

    return UpcomingEvents(
        next_earnings=earnings,
        next_dividend=dividend,
        ex_dividend=ex_div,
    )


def _parse_single_date(raw, today: date) -> date | None:
    """Parse a single date/datetime value, returning it only if it's upcoming."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        d = raw.date()
    elif isinstance(raw, date):
        d = raw
    else:
        return None
    return d if d >= today else None


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
        payload = r.json()
        result = _parse_finnhub(payload, today)
        logger.info("Finnhub earnings raw %s: rows=%d result=%s",
                     symbol, len((payload or {}).get("earningsCalendar", [])), result)
        return result
    except Exception as exc:
        logger.warning("Finnhub earnings failed for %s: %s", symbol, exc)
        return None


def _yf_calendar(symbol: str, today: date) -> UpcomingEvents:
    try:
        cal = yf.Ticker(symbol).calendar
        logger.info("yfinance calendar %s: keys=%s", symbol, list(cal.keys()) if isinstance(cal, dict) else type(cal).__name__)
    except Exception as exc:
        logger.warning("yfinance calendar failed for %s: %s", symbol, exc)
        return UpcomingEvents()
    return _parse_yf_calendar(cal, today)


_YF_TIMEOUT = 15  # seconds


async def _resolve_one(symbol: str, today: date) -> tuple[str, UpcomingEvents]:
    earnings: date | None = None
    yf_events = UpcomingEvents()
    earnings_source = "none"
    try:
        # Finnhub: earnings only
        if settings.finnhub_api_key:
            earnings = await _finnhub_next_earnings(symbol, today)
            if earnings is not None:
                earnings_source = "finnhub"

        # yfinance: earnings fallback + dividend dates (always fetched for dividends)
        try:
            yf_events = await asyncio.wait_for(
                asyncio.to_thread(_yf_calendar, symbol, today),
                timeout=_YF_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("yfinance calendar timed out for %s after %ds", symbol, _YF_TIMEOUT)

        if earnings is None and yf_events.next_earnings is not None:
            earnings = yf_events.next_earnings
            earnings_source = "yfinance"
    except Exception as exc:
        logger.warning("Event resolution failed for %s: %s", symbol, exc)

    result = UpcomingEvents(
        next_earnings=earnings,
        next_dividend=yf_events.next_dividend,
        ex_dividend=yf_events.ex_dividend,
    )
    _cache[symbol] = (today, result)
    logger.info("Events %s: earnings=%s(src=%s) div=%s ex_div=%s",
                symbol, earnings, earnings_source,
                yf_events.next_dividend, yf_events.ex_dividend)
    return symbol, result


async def get_upcoming_events(symbols: list[str]) -> dict[str, UpcomingEvents]:
    """Return {symbol: UpcomingEvents}, cached once per UTC day."""
    if not symbols:
        return {}

    if settings.scraper_mock_mode:
        base = date.today()
        return {
            s: UpcomingEvents(
                next_earnings=base + timedelta(
                    days=(int(hashlib.md5(s.encode()).hexdigest(), 16) % 60) + 1
                ),
                next_dividend=base + timedelta(
                    days=(int(hashlib.md5(b"div" + s.encode()).hexdigest(), 16) % 45) + 1
                ),
                ex_dividend=base + timedelta(
                    days=(int(hashlib.md5(b"exd" + s.encode()).hexdigest(), 16) % 40) + 1
                ),
            )
            for s in symbols
        }

    today = datetime.now(tz=timezone.utc).date()
    result: dict[str, UpcomingEvents] = {}
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
                logger.warning("Event resolution failed: %s", item)
                continue
            s, events = item
            result[s] = events

    return result


# Backwards-compatible wrapper
async def get_next_earnings(symbols: list[str]) -> dict[str, date | None]:
    events = await get_upcoming_events(symbols)
    return {s: ev.next_earnings for s, ev in events.items()}

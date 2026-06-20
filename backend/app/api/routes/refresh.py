"""
/api/v1/refresh  — orchestrates full scrape + indicator pipeline
/api/v1/last     — returns last successful result (shown on page load)
/api/v1/events   — SSE stream for live refresh status (start / done)
"""

import asyncio
import json
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.database import async_session
from app.models.last_refresh import LastRefresh
from app.services import indicators as ind_engine
from app.services.futu_scraper import NasdaqSnapshot, StockSnapshot, scraper
from app.services import quotes as quote_service
from app.services.historical import (
    ATHResult, PastValuesResult, YearHighResult,
    ensure_fresh, get_ath_status, get_past_values, get_year_high, _now_et,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache of the last successful refresh result (fast path; DB is the
# durable source of truth that survives Cloud Run cold starts / redeploys).
_last_result: dict[str, Any] | None = None

# In-memory event bus for SSE. Each broadcast bumps _sse_gen and sets the
# asyncio.Condition so every waiting SSE generator wakes, reads the new state,
# and pushes it to the browser. The generation counter avoids the set/clear
# race inherent in plain asyncio.Event.
_sse_lock = asyncio.Lock()
_sse_cond = asyncio.Condition(_sse_lock)
_sse_gen: int = 0
_sse_state: dict[str, Any] = {"type": "idle"}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class I4Model(BaseModel):
    today_value: float
    past_values: list[float]    # up to 15 days, oldest → newest
    avg: float
    ratio: float | None
    day_count: int
    dates: list[str]            # ISO trading date per past value (for tooltips)
    today_date: str | None      # ISO date of today's (live) bar


class I5Model(BaseModel):
    is_ath: bool
    ath_price: float | None
    ath_date: str | None
    days_since_ath: int | None
    year_high: float | None     # 52-week high price
    year_high_date: str | None  # date of 52-week high


class I6Model(BaseModel):
    nasdaq_from_open_pct: float
    nasdaq_from_prev_close_pct: float


class StockResult(BaseModel):
    rank: int
    symbol: str
    rt_price: float
    open_price: float
    prev_close: float
    today_high: float
    today_low: float
    scrape_error: str | None
    i1: float | None
    i2: float | None
    i3: float | None
    i4: I4Model
    i5: I5Model
    i6: I6Model


class NasdaqResult(BaseModel):
    rt_level: float
    open_level: float
    prev_close: float
    from_open_pct: float
    from_prev_close_pct: float
    error: str | None


class RefreshResponse(BaseModel):
    refreshed_at: str           # ISO 8601 with timezone
    nasdaq: NasdaqResult
    stocks: list[StockResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_date(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _build_stock_result(rank: int, indicators: ind_engine.StockIndicators) -> StockResult:
    i4 = indicators.i4
    i5 = indicators.i5
    i6 = indicators.i6
    return StockResult(
        rank=rank,
        symbol=indicators.symbol,
        rt_price=indicators.rt_price,
        open_price=indicators.open_price,
        prev_close=indicators.prev_close,
        today_high=indicators.today_high,
        today_low=indicators.today_low,
        scrape_error=indicators.scrape_error,
        i1=indicators.i1,
        i2=indicators.i2,
        i3=indicators.i3,
        i4=I4Model(
            today_value=i4.today_value,
            past_values=i4.past_values,
            avg=i4.avg,
            ratio=i4.ratio,
            day_count=i4.day_count,
            dates=i4.dates,
            today_date=i4.today_date,
        ),
        i5=I5Model(
            is_ath=i5.is_ath,
            ath_price=i5.ath_price,
            ath_date=_fmt_date(i5.ath_date),
            days_since_ath=i5.days_since_ath,
            year_high=i5.year_high,
            year_high_date=_fmt_date(i5.year_high_date),
        ),
        i6=I6Model(
            nasdaq_from_open_pct=i6.nasdaq_from_open_pct,
            nasdaq_from_prev_close_pct=i6.nasdaq_from_prev_close_pct,
        ),
    )


def _mock_history(symbol: str) -> tuple[PastValuesResult, ATHResult, YearHighResult]:
    """Return synthetic history/ATH/52W data for mock mode (no DB needed)."""
    import random, hashlib
    from datetime import date, timedelta
    rng = random.Random(int(hashlib.md5(symbol.encode()).hexdigest(), 16) % (2**32))
    base = 1_000_000_000 + rng.randint(0, 2_000_000_000)
    past = [base * (0.8 + rng.random() * 0.4) for _ in range(15)]
    avg = sum(past) / len(past)
    past_dates = [date.today() - timedelta(days=15 - i) for i in range(15)]
    history = PastValuesResult(values=past, avg=avg, count=15, dates=past_dates)
    ath_date = date.today() - timedelta(days=rng.randint(30, 500))
    ath = ATHResult(
        is_ath=rng.random() < 0.2,
        ath_price=base / 800_000,
        ath_date=ath_date,
        days_since_ath=(date.today() - ath_date).days,
    )
    yh_date = date.today() - timedelta(days=rng.randint(1, 180))
    year_high = YearHighResult(high_price=base / 900_000, high_date=yh_date)
    return history, ath, year_high


async def _broadcast(state: dict[str, Any]) -> None:
    """Wake all SSE listeners with a new state."""
    global _sse_state, _sse_gen
    async with _sse_cond:
        _sse_state = state
        _sse_gen += 1
        _sse_cond.notify_all()


# A refresh that hangs longer than this lets the next caller steal the lock,
# so a crashed pipeline can never wedge refreshes permanently. Comfortably
# above the worst-case pipeline runtime (~60-90s) and the scraper timeouts.
_LOCK_STALE_AFTER = timedelta(minutes=3)


async def _acquire_lock() -> bool:
    """Atomically claim the single-flight refresh lock across all instances.

    Returns True if this caller acquired it, False if a refresh is already
    running elsewhere (another tab, another user, or the cron job). The atomic
    UPDATE ... WHERE means exactly one concurrent caller can win.
    """
    if settings.scraper_mock_mode:
        return True
    now = datetime.now(tz=timezone.utc)
    stale_before = now - _LOCK_STALE_AFTER
    try:
        async with async_session() as session:
            # Claim only if not currently refreshing, or the existing lock is stale.
            result = await session.execute(
                update(LastRefresh)
                .where(
                    LastRefresh.id == 1,
                    or_(
                        LastRefresh.is_refreshing.is_(False),
                        LastRefresh.refresh_started_at.is_(None),
                        LastRefresh.refresh_started_at < stale_before,
                    ),
                )
                .values(is_refreshing=True, refresh_started_at=now)
            )
            if result.rowcount == 1:
                await session.commit()
                return True

            # rowcount 0 → either the row doesn't exist yet (first run) or the
            # lock is genuinely held. Try to insert; if it already exists, held.
            await session.rollback()
            if await session.get(LastRefresh, 1) is None:
                try:
                    session.add(LastRefresh(
                        id=1, payload="{}", refreshed_at=now,
                        is_refreshing=True, refresh_started_at=now,
                    ))
                    await session.commit()
                    return True
                except IntegrityError:
                    await session.rollback()  # lost the insert race
            return False
    except Exception as exc:
        logger.warning("Failed to acquire refresh lock: %s", exc)
        # On DB failure, don't block refreshes entirely — fall back to allowing.
        return True


async def _release_lock() -> None:
    """Clear the lock (failure path). Success path clears it via _persist_last."""
    if settings.scraper_mock_mode:
        return
    try:
        async with async_session() as session:
            await session.execute(
                update(LastRefresh)
                .where(LastRefresh.id == 1)
                .values(is_refreshing=False)
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to release refresh lock: %s", exc)


async def _persist_last(payload: dict[str, Any]) -> None:
    """Upsert the single last_refresh row so /last survives cold starts."""
    if settings.scraper_mock_mode:
        return
    try:
        async with async_session() as session:
            row = await session.get(LastRefresh, 1)
            now = datetime.now(tz=timezone.utc)
            if row is None:
                session.add(LastRefresh(
                    id=1, payload=json.dumps(payload),
                    refreshed_at=now, is_refreshing=False,
                ))
            else:
                row.payload = json.dumps(payload)
                row.refreshed_at = now
                row.is_refreshing = False
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to persist last_refresh: %s", exc)


async def _load_last() -> dict[str, Any] | None:
    """Read the persisted last_refresh row (DB), falling back to memory."""
    if _last_result is not None:
        return _last_result
    if settings.scraper_mock_mode:
        return None
    try:
        async with async_session() as session:
            row = (await session.execute(select(LastRefresh).limit(1))).scalar_one_or_none()
            if row is not None:
                parsed = json.loads(row.payload)
                # A row created purely to hold the lock (first ever run) has an
                # empty "{}" payload — treat that as "no data yet", not a result.
                if isinstance(parsed, dict) and parsed.get("stocks"):
                    return parsed
    except Exception as exc:
        logger.warning("Failed to load last_refresh from DB: %s", exc)
    return None


async def _load_refresh_status() -> dict[str, Any]:
    """Read the current refresh status from DB (cross-instance)."""
    if settings.scraper_mock_mode:
        return {"is_refreshing": False, "refreshed_at": None}
    try:
        async with async_session() as session:
            row = (await session.execute(select(LastRefresh).limit(1))).scalar_one_or_none()
            if row is not None:
                return {
                    "is_refreshing": row.is_refreshing,
                    "refreshed_at": row.refreshed_at.isoformat() if row.refreshed_at else None,
                }
    except Exception as exc:
        logger.warning("Failed to load refresh status: %s", exc)
    return {"is_refreshing": False, "refreshed_at": None}


async def _get_nasdaq() -> NasdaqSnapshot:
    """Real-time NASDAQ level, preferring Futu's live index page.

    Futu's .IXIC-US page is live and matches the real-time basis of the
    per-stock Finnhub quotes. yfinance fast_info is ~15 min delayed, so it's
    kept only as a backstop when the Futu scrape fails or yields an empty level.
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        snap = await scraper.get_nasdaq_snapshot()
        log.info("Futu NASDAQ: rt=%.2f open=%.2f prev=%.2f err=%s",
                 snap.rt_level, snap.open_level, snap.prev_close, snap.error)
        if snap.rt_level > 0:
            return snap
    except Exception as exc:
        log.warning("Futu NASDAQ scrape exception: %s", exc)
    log.info("Falling back to yfinance for NASDAQ")
    return await quote_service.get_nasdaq_snapshot()


def _i4_from_intraday(
    intraday: dict[date, float],
    today: date,
    db_history: PastValuesResult,
    snapshot: StockSnapshot,
) -> tuple[PastValuesResult, float]:
    """Prefer bar-aggregated turnover (true VWAP basis) for I4; fall back to DB.

    Returns (history, today_value). History and today are taken from the *same*
    basis so the bar chart is apples-to-apples: if there's enough intraday
    history we use it for both; otherwise we keep the DB close×volume history
    and the snapshot's close×volume today.
    """
    completed = sorted(d for d in intraday if d < today)
    if len(completed) >= 3:
        last = completed[-15:]
        values = [intraday[d] for d in last]
        avg = sum(values) / len(values) if values else 0.0
        history = PastValuesResult(values=values, avg=avg, count=len(values), dates=last)
        today_value = intraday.get(today, snapshot.today_value)
        return history, today_value
    # Not enough intraday history → stay on the existing close×volume basis.
    return db_history, snapshot.today_value


async def _process_symbol(
    symbol: str,
    snapshot: StockSnapshot,
    nasdaq: NasdaqSnapshot,
    now_et: datetime,
    intraday_turnover: dict[date, float] | None = None,
) -> ind_engine.StockIndicators:
    """Ensure complete history, then compute all indicators."""
    if settings.scraper_mock_mode:
        history, ath, year_high = _mock_history(symbol)
    else:
        # Backfill/normalise history first so ATH + 52-week high are computed
        # over the complete, correctly-adjusted series.
        await ensure_fresh(symbol, now_et)
        history, ath, year_high = await asyncio.gather(
            get_past_values(symbol, days=15),
            get_ath_status(symbol, snapshot.today_high, now_et),
            get_year_high(symbol, snapshot.today_high, now_et),
        )
        # Upgrade I4 to the accurate bar-aggregated turnover when available.
        history, today_value = _i4_from_intraday(
            intraday_turnover or {}, now_et.date(), history, snapshot
        )
        snapshot = replace(snapshot, today_value=today_value)
    return ind_engine.compute_all(
        snapshot, history, ath, year_high, nasdaq,
        today_date=now_et.date().isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=RefreshResponse)
async def refresh() -> RefreshResponse:
    """
    Full pipeline:
    1. Scrape top 10 symbols from Futu
    2. Scrape all 10 stock pages + NASDAQ in parallel
    3. Seed any new symbols from yfinance
    4. Compute I1–I6 for each stock
    5. Cache and return result
    """
    global _last_result

    # Single-flight: only one refresh may run at a time across all instances,
    # whether triggered by a user click or the cron job. If one is already
    # running, return 409 — the caller will receive the result via SSE.
    if not await _acquire_lock():
        raise HTTPException(status_code=409, detail="A refresh is already in progress")

    # Signal SSE clients (this instance instantly; other instances via DB poll).
    await _broadcast({"type": "refresh_start"})

    try:
        return await _do_refresh()
    except Exception:
        await _release_lock()
        await _broadcast({"type": "idle"})
        raise


async def _do_refresh() -> RefreshResponse:
    global _last_result

    # Step 1: get candidates (Futu scrape — Playwright browser starts here)
    symbols = await scraper.get_top_active_symbols()
    if not symbols:
        raise HTTPException(status_code=502, detail="Failed to fetch candidates from Futu")

    # Step 1b: NASDAQ from Futu while the browser is still warm (sequential,
    # same Playwright instance). Falls back to yfinance if the scrape fails.
    nasdaq = await _get_nasdaq()

    # Step 2: fetch quotes (Finnhub) concurrently — no Playwright needed
    snapshots = await quote_service.get_all_snapshots(symbols)

    if all(s.error for s in snapshots):
        raise HTTPException(status_code=502, detail=f"All quote fetches failed: {snapshots[0].error}")

    # Step 2b: one batched intraday pull → accurate bar-aggregated turnover for
    # I4 (true VWAP basis). Empty dict on failure → close×volume fallback.
    intraday_turnover = await quote_service.get_intraday_turnover(symbols)

    # Step 3+4: backfill history + compute indicators for each symbol.
    # One shared "now" so freshness, ATH and 52-week high all agree on the clock.
    now_et = _now_et()
    tasks = [
        _process_symbol(
            snap.symbol, snap, nasdaq, now_et,
            intraday_turnover.get(snap.symbol),
        )
        for snap in snapshots
    ]
    all_indicators = await asyncio.gather(*tasks)

    # Build response
    nasdaq_result = NasdaqResult(
        rt_level=nasdaq.rt_level,
        open_level=nasdaq.open_level,
        prev_close=nasdaq.prev_close,
        from_open_pct=(
            (nasdaq.rt_level - nasdaq.open_level) / nasdaq.open_level
            if nasdaq.open_level > 0 else 0.0
        ),
        from_prev_close_pct=(
            (nasdaq.rt_level - nasdaq.prev_close) / nasdaq.prev_close
            if nasdaq.prev_close > 0 else 0.0
        ),
        error=nasdaq.error,
    )

    stock_results = [
        _build_stock_result(rank=i + 1, indicators=ind)
        for i, ind in enumerate(all_indicators)
    ]

    response = RefreshResponse(
        refreshed_at=datetime.now(tz=timezone.utc).isoformat(),
        nasdaq=nasdaq_result,
        stocks=stock_results,
    )

    # Cache in memory (fast path) and persist to DB (durable across cold starts).
    # Also clears is_refreshing and broadcasts the finished data to SSE clients.
    _last_result = response.model_dump()
    await _persist_last(_last_result)
    await _broadcast({"type": "refresh_done", "data": _last_result})
    return response


@router.get("/last", response_model=RefreshResponse)
async def get_last() -> RefreshResponse:
    """Return the most recent refresh result — from DB so it survives cold starts."""
    last = await _load_last()
    if last is None:
        raise HTTPException(status_code=404, detail="No data yet — click Refresh Data")
    return RefreshResponse(**last)


@router.get("/status")
async def get_status() -> dict:
    """Lightweight poll: is a refresh in-flight? When was the last one?"""
    status = await _load_refresh_status()
    return status


@router.get("/events")
async def events(request: Request):
    """SSE stream. Pushes refresh_start / refresh_done events in real time.

    Same-instance refreshes are notified instantly via the in-memory event.
    For cross-instance (scheduler hits a different Cloud Run instance), the
    generator also polls the DB every 3s to detect `is_refreshing` changes.
    """
    async def stream():
        last_refreshed_at: str | None = None
        last_was_refreshing: bool | None = None
        seen_gen = _sse_gen

        # Send the current status immediately so the client syncs on connect.
        status = await _load_refresh_status()
        last_was_refreshing = status["is_refreshing"]
        last_refreshed_at = status.get("refreshed_at")
        if status["is_refreshing"]:
            yield {"event": "refresh_start", "data": "{}"}
        yield {"event": "status", "data": json.dumps(status)}

        while True:
            if await request.is_disconnected():
                break

            # Wait for an in-memory broadcast (fast, same-instance) or fall
            # back to a 3s DB poll (cross-instance, scheduler on another pod).
            got_broadcast = False
            try:
                async with asyncio.timeout(3.0):
                    async with _sse_cond:
                        await _sse_cond.wait_for(lambda: _sse_gen > seen_gen)
                        seen_gen = _sse_gen
                        state = _sse_state
                got_broadcast = True
                if state.get("type") == "refresh_start":
                    yield {"event": "refresh_start", "data": "{}"}
                elif state.get("type") == "refresh_done":
                    yield {"event": "refresh_done", "data": json.dumps(state.get("data", {}))}
            except asyncio.TimeoutError:
                pass

            if got_broadcast:
                continue

            # DB poll fallback: detect state changes made by other instances.
            try:
                status = await _load_refresh_status()
                is_refreshing = status["is_refreshing"]
                refreshed_at = status.get("refreshed_at")

                if is_refreshing and last_was_refreshing is not True:
                    yield {"event": "refresh_start", "data": "{}"}
                    last_was_refreshing = True
                elif not is_refreshing and last_was_refreshing is True:
                    last = await _load_last()
                    yield {"event": "refresh_done", "data": json.dumps(last or {})}
                    last_was_refreshing = False
                    last_refreshed_at = refreshed_at
                elif not is_refreshing and refreshed_at != last_refreshed_at and last_refreshed_at is not None:
                    last = await _load_last()
                    yield {"event": "refresh_done", "data": json.dumps(last or {})}
                    last_refreshed_at = refreshed_at

                last_was_refreshing = is_refreshing
                last_refreshed_at = refreshed_at
            except Exception:
                pass

    return EventSourceResponse(stream())

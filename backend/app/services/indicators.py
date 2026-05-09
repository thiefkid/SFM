"""
Indicator computation engine.

I1: (RT price - open) / open
I2: (RT price - prev close) / prev close
I3: (RT price - open) / (today high - open)   → None if high == open
I4: today trading value vs past 5 days
I5: all-time high status
I6: NASDAQ % change from open; NASDAQ % change from prev close
"""

from dataclasses import dataclass
from datetime import date

from app.services.futu_scraper import NasdaqSnapshot, StockSnapshot
from app.services.historical import ATHResult, PastValuesResult, YearHighResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class I4Result:
    today_value: float
    past_values: list[float]    # up to 15 days, oldest → newest (for bar chart)
    avg: float
    ratio: float | None         # today / avg; None if avg is 0
    day_count: int              # actual days of history available


@dataclass
class I5Result:
    is_ath: bool
    ath_price: float | None
    ath_date: date | None
    days_since_ath: int | None
    year_high: float | None     # 52-week high
    year_high_date: date | None


@dataclass
class I6Result:
    nasdaq_from_open_pct: float
    nasdaq_from_prev_close_pct: float


@dataclass
class StockIndicators:
    symbol: str
    rt_price: float
    scrape_error: str | None

    # Raw snapshot values (for debug display and candle chart)
    open_price: float
    prev_close: float
    today_high: float
    today_low: float

    # Indicators
    i1: float | None            # intraday gain from open
    i2: float | None            # day change from yesterday
    i3: float | None            # position in day's range (None if no range yet)
    i4: I4Result
    i5: I5Result
    i6: I6Result


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def compute_i1(rt_price: float, open_price: float) -> float | None:
    """(RT - open) / open"""
    if open_price == 0:
        return None
    return (rt_price - open_price) / open_price


def compute_i2(rt_price: float, prev_close: float) -> float | None:
    """(RT - prev close) / prev close"""
    if prev_close == 0:
        return None
    return (rt_price - prev_close) / prev_close


def compute_i3(rt_price: float, open_price: float, today_high: float) -> float | None:
    """
    (RT - open) / (today high - open)
    Returns None when high == open (no intraday range yet — pre-market or just opened).
    Returns negative when RT price is below open.
    """
    denominator = today_high - open_price
    if denominator == 0:
        return None
    return (rt_price - open_price) / denominator


def compute_i4(today_value: float, history: PastValuesResult) -> I4Result:
    """Today's trading value vs past 15 days (for bar chart)."""
    ratio = (today_value / history.avg) if history.avg > 0 else None
    return I4Result(
        today_value=today_value,
        past_values=history.values,
        avg=history.avg,
        ratio=ratio,
        day_count=history.count,
    )


def compute_i5(
    ath: ATHResult | None,
    today_high: float,
    year_high: YearHighResult | None,
) -> I5Result:
    """All-time high status + 52-week high."""
    year_high_price = year_high.high_price if year_high else None
    year_high_date = year_high.high_date if year_high else None

    if ath is None:
        return I5Result(
            is_ath=False, ath_price=None, ath_date=None, days_since_ath=None,
            year_high=year_high_price, year_high_date=year_high_date,
        )

    is_ath = today_high > ath.ath_price
    if is_ath:
        return I5Result(
            is_ath=True, ath_price=today_high, ath_date=date.today(), days_since_ath=0,
            year_high=year_high_price, year_high_date=year_high_date,
        )

    return I5Result(
        is_ath=False,
        ath_price=ath.ath_price,
        ath_date=ath.ath_date,
        days_since_ath=ath.days_since_ath,
        year_high=year_high_price,
        year_high_date=year_high_date,
    )


def compute_i6(nasdaq: NasdaqSnapshot) -> I6Result:
    """NASDAQ % change from open and from prev close."""
    from_open = (
        (nasdaq.rt_level - nasdaq.open_level) / nasdaq.open_level
        if nasdaq.open_level > 0 else 0.0
    )
    from_prev_close = (
        (nasdaq.rt_level - nasdaq.prev_close) / nasdaq.prev_close
        if nasdaq.prev_close > 0 else 0.0
    )
    return I6Result(
        nasdaq_from_open_pct=from_open,
        nasdaq_from_prev_close_pct=from_prev_close,
    )


def compute_all(
    snapshot: StockSnapshot,
    history: PastValuesResult,
    ath: ATHResult | None,
    year_high: YearHighResult | None,
    nasdaq: NasdaqSnapshot,
) -> StockIndicators:
    """Compute all 6 indicators for a single stock."""
    return StockIndicators(
        symbol=snapshot.symbol,
        rt_price=snapshot.rt_price,
        scrape_error=snapshot.error,
        open_price=snapshot.open_price,
        prev_close=snapshot.prev_close,
        today_high=snapshot.today_high,
        today_low=snapshot.today_low,
        i1=compute_i1(snapshot.rt_price, snapshot.open_price),
        i2=compute_i2(snapshot.rt_price, snapshot.prev_close),
        i3=compute_i3(snapshot.rt_price, snapshot.open_price, snapshot.today_high),
        i4=compute_i4(snapshot.today_value, history),
        i5=compute_i5(ath, snapshot.today_high, year_high),
        i6=compute_i6(nasdaq),
    )

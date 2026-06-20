"""
US equity market session status with holiday awareness.

Sessions (all times Eastern):
  - Pre-market:    04:00 – 09:30
  - Regular:       09:30 – 16:00
  - After-hours:   16:00 – 20:00
  - Closed:        20:00 – 04:00, weekends, holidays

Early-close days (13:00 ET): day before Independence Day, Black Friday,
Christmas Eve. On these days regular session ends at 13:00 and after-hours
runs 13:00–15:00 (per exchange rules, though we simplify to 13:00–17:00).
"""

from datetime import date, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# --------------------------------------------------------------------------
# US market holidays (NYSE/NASDAQ observed schedule)
# --------------------------------------------------------------------------

def _us_market_holidays(year: int) -> set[date]:
    """Compute NYSE/NASDAQ holidays for a given year."""
    holidays: set[date] = set()

    # New Year's Day
    nyd = date(year, 1, 1)
    holidays.add(_observe(nyd))

    # MLK Day — 3rd Monday of January
    holidays.add(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day — 3rd Monday of February
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday — 2 days before Easter Sunday
    holidays.add(_easter(year) - timedelta(days=2))

    # Memorial Day — last Monday of May
    holidays.add(_last_weekday(year, 5, 0))

    # Juneteenth
    holidays.add(_observe(date(year, 6, 19)))

    # Independence Day
    holidays.add(_observe(date(year, 7, 4)))

    # Labor Day — 1st Monday of September
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving — 4th Thursday of November
    holidays.add(_nth_weekday(year, 11, 3, 4))

    # Christmas
    holidays.add(_observe(date(year, 12, 25)))

    return holidays


def _early_close_dates(year: int) -> set[date]:
    """Days when the market closes at 13:00 ET instead of 16:00."""
    early: set[date] = set()

    # Day before Independence Day (if it's a weekday)
    jul4 = _observe(date(year, 7, 4))
    day_before = jul4 - timedelta(days=1)
    if day_before.weekday() < 5:
        early.add(day_before)

    # Black Friday — day after Thanksgiving
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    early.add(thanksgiving + timedelta(days=1))

    # Christmas Eve (if it's a weekday and not a holiday)
    xmas_eve = date(year, 12, 24)
    if xmas_eve.weekday() < 5 and xmas_eve not in _us_market_holidays(year):
        early.add(xmas_eve)

    return early


# --------------------------------------------------------------------------
# Date helpers
# --------------------------------------------------------------------------

def _observe(d: date) -> date:
    """If a holiday falls on Sat→observed Fri, Sun→observed Mon."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of weekday (0=Mon) in the given month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday (0=Mon) in the given month."""
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _easter(year: int) -> date:
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


# --------------------------------------------------------------------------
# Caches (per-year, never stale within a calendar year)
# --------------------------------------------------------------------------

_holiday_cache: dict[int, set[date]] = {}
_early_close_cache: dict[int, set[date]] = {}


def _holidays_for(year: int) -> set[date]:
    if year not in _holiday_cache:
        _holiday_cache[year] = _us_market_holidays(year)
    return _holiday_cache[year]


def _early_closes_for(year: int) -> set[date]:
    if year not in _early_close_cache:
        _early_close_cache[year] = _early_close_dates(year)
    return _early_close_cache[year]


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

# Session boundaries (ET)
_PRE_MARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)
_AFTER_HOURS_END = time(20, 0)
_EARLY_AFTER_HOURS_END = time(17, 0)


def get_market_session(now_et) -> dict:
    """Return current market session status.

    Returns dict with:
      session:     "pre_market" | "regular" | "after_hours" | "closed"
      label:       Human-readable label
      is_holiday:  True if today is a market holiday
      holiday_name: Name of the holiday (if applicable)
      next_open:   ISO datetime of next regular session open (if closed)
    """
    today = now_et.date()
    t = now_et.time()
    wd = today.weekday()

    holidays = _holidays_for(today.year)
    early_closes = _early_closes_for(today.year)

    # Check if today is a holiday
    if today in holidays:
        name = _holiday_name(today)
        return {
            "session": "closed",
            "label": f"Closed — {name}",
            "is_holiday": True,
            "holiday_name": name,
            "next_open": _next_open(today).isoformat(),
        }

    # Weekend
    if wd >= 5:
        return {
            "session": "closed",
            "label": "Closed — Weekend",
            "is_holiday": False,
            "holiday_name": None,
            "next_open": _next_open(today).isoformat(),
        }

    is_early = today in early_closes
    close_time = _EARLY_CLOSE if is_early else _REGULAR_CLOSE
    ah_end = _EARLY_AFTER_HOURS_END if is_early else _AFTER_HOURS_END

    if t < _PRE_MARKET_OPEN:
        return {
            "session": "closed",
            "label": "Closed — Overnight",
            "is_holiday": False,
            "holiday_name": None,
            "next_open": None,
        }

    if t < _REGULAR_OPEN:
        return {
            "session": "pre_market",
            "label": "Pre-Market (4:00–9:30 ET)",
            "is_holiday": False,
            "holiday_name": None,
            "next_open": None,
        }

    if t < close_time:
        suffix = " (early close 1:00 PM)" if is_early else ""
        return {
            "session": "regular",
            "label": f"Regular Session{suffix}",
            "is_holiday": False,
            "holiday_name": None,
            "next_open": None,
        }

    if t < ah_end:
        return {
            "session": "after_hours",
            "label": "After Hours",
            "is_holiday": False,
            "holiday_name": None,
            "next_open": _next_open(today).isoformat(),
        }

    return {
        "session": "closed",
        "label": "Closed — Overnight",
        "is_holiday": False,
        "holiday_name": None,
        "next_open": _next_open(today).isoformat(),
    }


def _next_open(from_date: date) -> date:
    """Find the next trading day (skipping weekends and holidays)."""
    d = from_date + timedelta(days=1)
    for _ in range(10):
        if d.weekday() < 5 and d not in _holidays_for(d.year):
            return d
        d += timedelta(days=1)
    return d


def _holiday_name(d: date) -> str:
    """Return the name of the holiday for display."""
    year = d.year
    names = [
        (_observe(date(year, 1, 1)), "New Year's Day"),
        (_nth_weekday(year, 1, 0, 3), "MLK Day"),
        (_nth_weekday(year, 2, 0, 3), "Presidents' Day"),
        (_easter(year) - timedelta(days=2), "Good Friday"),
        (_last_weekday(year, 5, 0), "Memorial Day"),
        (_observe(date(year, 6, 19)), "Juneteenth"),
        (_observe(date(year, 7, 4)), "Independence Day"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving"),
        (_observe(date(year, 12, 25)), "Christmas"),
    ]
    for hd, name in names:
        if hd == d:
            return name
    return "Market Holiday"

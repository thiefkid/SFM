"""
Tests for US market session status with holiday awareness.

Verifies:
  - Regular session hours
  - Pre-market / after-hours windows
  - Weekend detection
  - US market holidays (fixed + floating)
  - Early close days
  - Next-open calculation across holidays
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.market_session import (
    _easter,
    _holidays_for,
    _early_closes_for,
    _next_open,
    get_market_session,
)

ET = ZoneInfo("America/New_York")


def _dt(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ET)


# ---------------------------------------------------------------------------
# Easter computation
# ---------------------------------------------------------------------------

class TestEaster:
    def test_2024(self):
        assert _easter(2024) == date(2024, 3, 31)

    def test_2025(self):
        assert _easter(2025) == date(2025, 4, 20)

    def test_2026(self):
        assert _easter(2026) == date(2026, 4, 5)


# ---------------------------------------------------------------------------
# Holiday list
# ---------------------------------------------------------------------------

class TestHolidays:
    def test_2026_holidays(self):
        h = _holidays_for(2026)
        assert date(2026, 1, 1) in h      # New Year's
        assert date(2026, 1, 19) in h     # MLK Day
        assert date(2026, 2, 16) in h     # Presidents' Day
        assert date(2026, 4, 3) in h      # Good Friday (Easter Apr 5)
        assert date(2026, 5, 25) in h     # Memorial Day
        assert date(2026, 6, 19) in h     # Juneteenth
        assert date(2026, 7, 3) in h      # Independence Day (Jul 4 is Sat → observed Fri)
        assert date(2026, 9, 7) in h      # Labor Day
        assert date(2026, 11, 26) in h    # Thanksgiving
        assert date(2026, 12, 25) in h    # Christmas

    def test_holiday_sunday_observed_monday(self):
        # 2022: July 4 is Monday — no shift needed
        h = _holidays_for(2022)
        assert date(2022, 7, 4) in h

    def test_holiday_saturday_observed_friday(self):
        # 2026: July 4 is Saturday → observed Friday July 3
        h = _holidays_for(2026)
        assert date(2026, 7, 3) in h
        assert date(2026, 7, 4) not in h

    def test_juneteenth_sunday_observed_monday(self):
        # 2022: June 19 is Sunday → observed Monday June 20
        h = _holidays_for(2022)
        assert date(2022, 6, 20) in h


# ---------------------------------------------------------------------------
# Early close days
# ---------------------------------------------------------------------------

class TestEarlyClose:
    def test_black_friday(self):
        # Thanksgiving 2026 = Nov 26, Black Friday = Nov 27
        ec = _early_closes_for(2026)
        assert date(2026, 11, 27) in ec

    def test_christmas_eve_weekday(self):
        # 2026: Dec 24 is Thursday → early close
        ec = _early_closes_for(2026)
        assert date(2026, 12, 24) in ec


# ---------------------------------------------------------------------------
# Session detection
# ---------------------------------------------------------------------------

class TestGetMarketSession:
    def test_pre_market(self):
        s = get_market_session(_dt(2026, 6, 15, 7, 0))  # Monday 7am
        assert s["session"] == "pre_market"

    def test_regular_session(self):
        s = get_market_session(_dt(2026, 6, 15, 10, 0))  # Monday 10am
        assert s["session"] == "regular"

    def test_regular_session_at_open(self):
        s = get_market_session(_dt(2026, 6, 15, 9, 30))
        assert s["session"] == "regular"

    def test_after_hours(self):
        s = get_market_session(_dt(2026, 6, 15, 17, 0))  # Monday 5pm
        assert s["session"] == "after_hours"

    def test_closed_overnight(self):
        s = get_market_session(_dt(2026, 6, 15, 2, 0))  # Monday 2am
        assert s["session"] == "closed"

    def test_closed_late_night(self):
        s = get_market_session(_dt(2026, 6, 15, 21, 0))  # Monday 9pm
        assert s["session"] == "closed"

    def test_weekend_saturday(self):
        s = get_market_session(_dt(2026, 6, 20, 12, 0))  # Saturday
        assert s["session"] == "closed"
        assert "Weekend" in s["label"]

    def test_weekend_sunday(self):
        s = get_market_session(_dt(2026, 6, 21, 12, 0))  # Sunday
        assert s["session"] == "closed"

    def test_holiday(self):
        s = get_market_session(_dt(2026, 12, 25, 12, 0))  # Christmas
        assert s["session"] == "closed"
        assert s["is_holiday"] is True
        assert s["holiday_name"] == "Christmas"

    def test_independence_day_observed(self):
        # 2026: Jul 4 is Sat → observed Fri Jul 3
        s = get_market_session(_dt(2026, 7, 3, 12, 0))
        assert s["session"] == "closed"
        assert s["is_holiday"] is True
        assert "Independence" in s["holiday_name"]

    def test_early_close_day_regular_before_1pm(self):
        # Black Friday 2026 = Nov 27, 12:30 → still regular
        s = get_market_session(_dt(2026, 11, 27, 12, 30))
        assert s["session"] == "regular"
        assert "early close" in s["label"]

    def test_early_close_day_after_hours_at_1pm(self):
        # Black Friday 2026 = Nov 27, 13:00 → after hours
        s = get_market_session(_dt(2026, 11, 27, 13, 0))
        assert s["session"] == "after_hours"

    def test_early_close_closed_after_5pm(self):
        # Black Friday 2026 = Nov 27, 17:00 → closed (early AH ends at 17:00)
        s = get_market_session(_dt(2026, 11, 27, 17, 0))
        assert s["session"] == "closed"


# ---------------------------------------------------------------------------
# Next open
# ---------------------------------------------------------------------------

class TestNextOpen:
    def test_friday_to_monday(self):
        assert _next_open(date(2026, 6, 19)) == date(2026, 6, 22)  # Fri → Mon

    def test_skips_holiday(self):
        # Thanksgiving 2026 = Nov 26 (Thu). Next open after Wed Nov 25:
        # Nov 26 = holiday, Nov 27 = early close but still open
        assert _next_open(date(2026, 11, 25)) == date(2026, 11, 27)

    def test_skips_weekend_and_holiday(self):
        # Christmas 2026 = Dec 25 (Fri). Next open after Dec 24:
        # Dec 25 = holiday, Dec 26 = Sat, Dec 27 = Sun → Dec 28
        assert _next_open(date(2026, 12, 24)) == date(2026, 12, 28)

"""
Tests for the next-earnings-date service.

Focus: the parsing of Finnhub and yfinance responses must pick the earliest
*upcoming* date and never a past one, and degrade to None cleanly so the
countdown can't show a stale/wrong date.
"""

from datetime import date, datetime

import httpx
import pytest

from app.services import earnings as earnings_mod
from app.services.earnings import (
    _earliest_future,
    _parse_finnhub,
    _parse_yf_calendar,
    get_next_earnings,
)

TODAY = date(2026, 6, 20)


# ---------------------------------------------------------------------------
# _earliest_future
# ---------------------------------------------------------------------------

class TestEarliestFuture:
    def test_picks_earliest_future(self):
        dates = [date(2026, 8, 1), date(2026, 7, 1), date(2026, 9, 1)]
        assert _earliest_future(dates, TODAY) == date(2026, 7, 1)

    def test_ignores_past(self):
        dates = [date(2026, 1, 1), date(2026, 7, 1)]
        assert _earliest_future(dates, TODAY) == date(2026, 7, 1)

    def test_today_counts_as_future(self):
        assert _earliest_future([TODAY], TODAY) == TODAY

    def test_all_past_returns_none(self):
        assert _earliest_future([date(2026, 1, 1)], TODAY) is None

    def test_empty_returns_none(self):
        assert _earliest_future([], TODAY) is None


# ---------------------------------------------------------------------------
# Finnhub parsing
# ---------------------------------------------------------------------------

class TestParseFinnhub:
    def test_picks_earliest_upcoming(self):
        payload = {"earningsCalendar": [
            {"date": "2026-08-01", "symbol": "AAPL"},
            {"date": "2026-07-15", "symbol": "AAPL"},
        ]}
        assert _parse_finnhub(payload, TODAY) == date(2026, 7, 15)

    def test_skips_past_rows(self):
        payload = {"earningsCalendar": [
            {"date": "2026-02-01", "symbol": "AAPL"},
            {"date": "2026-07-15", "symbol": "AAPL"},
        ]}
        assert _parse_finnhub(payload, TODAY) == date(2026, 7, 15)

    def test_empty_calendar(self):
        assert _parse_finnhub({"earningsCalendar": []}, TODAY) is None

    def test_missing_key(self):
        assert _parse_finnhub({}, TODAY) is None

    def test_none_payload(self):
        assert _parse_finnhub(None, TODAY) is None

    def test_bad_date_string_skipped(self):
        payload = {"earningsCalendar": [
            {"date": "not-a-date", "symbol": "AAPL"},
            {"date": "2026-07-15", "symbol": "AAPL"},
        ]}
        assert _parse_finnhub(payload, TODAY) == date(2026, 7, 15)

    def test_missing_date_field_skipped(self):
        payload = {"earningsCalendar": [
            {"symbol": "AAPL"},
            {"date": "2026-07-15", "symbol": "AAPL"},
        ]}
        assert _parse_finnhub(payload, TODAY) == date(2026, 7, 15)


# ---------------------------------------------------------------------------
# yfinance calendar parsing
# ---------------------------------------------------------------------------

class TestParseYfCalendar:
    def test_single_date_list(self):
        cal = {"Earnings Date": [date(2026, 7, 30)]}
        assert _parse_yf_calendar(cal, TODAY) == date(2026, 7, 30)

    def test_estimated_range_picks_earliest_future(self):
        cal = {"Earnings Date": [date(2026, 7, 30), date(2026, 8, 4)]}
        assert _parse_yf_calendar(cal, TODAY) == date(2026, 7, 30)

    def test_datetime_values_converted(self):
        cal = {"Earnings Date": [datetime(2026, 7, 30, 16, 0)]}
        assert _parse_yf_calendar(cal, TODAY) == date(2026, 7, 30)

    def test_past_date_returns_none(self):
        cal = {"Earnings Date": [date(2026, 1, 1)]}
        assert _parse_yf_calendar(cal, TODAY) is None

    def test_scalar_date(self):
        cal = {"Earnings Date": date(2026, 7, 30)}
        assert _parse_yf_calendar(cal, TODAY) == date(2026, 7, 30)

    def test_empty_dict(self):
        assert _parse_yf_calendar({}, TODAY) is None

    def test_none(self):
        assert _parse_yf_calendar(None, TODAY) is None

    def test_missing_earnings_date_key(self):
        assert _parse_yf_calendar({"Dividend Date": date(2026, 7, 1)}, TODAY) is None


# ---------------------------------------------------------------------------
# get_next_earnings — orchestration
# ---------------------------------------------------------------------------

class TestGetNextEarnings:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        earnings_mod._cache.clear()
        yield
        earnings_mod._cache.clear()

    @pytest.mark.asyncio
    async def test_empty_symbols(self):
        assert await get_next_earnings([]) == {}

    @pytest.mark.asyncio
    async def test_falls_back_to_yfinance_when_finnhub_empty(self, monkeypatch):
        async def fake_finnhub(symbol, today):
            return None

        def fake_yf(symbol, today):
            return date(2026, 7, 15)

        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(earnings_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(earnings_mod, "_finnhub_next_earnings", fake_finnhub)
        monkeypatch.setattr(earnings_mod, "_yf_next_earnings", fake_yf)

        result = await get_next_earnings(["AAPL"])
        assert result["AAPL"] == date(2026, 7, 15)

    @pytest.mark.asyncio
    async def test_prefers_finnhub_over_yfinance(self, monkeypatch):
        async def fake_finnhub(symbol, today):
            return date(2026, 7, 10)

        def fake_yf(symbol, today):
            raise AssertionError("yfinance should not be called when Finnhub succeeds")

        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(earnings_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(earnings_mod, "_finnhub_next_earnings", fake_finnhub)
        monkeypatch.setattr(earnings_mod, "_yf_next_earnings", fake_yf)

        result = await get_next_earnings(["AAPL"])
        assert result["AAPL"] == date(2026, 7, 10)

    @pytest.mark.asyncio
    async def test_cached_within_same_day(self, monkeypatch):
        calls = {"n": 0}

        async def fake_finnhub(symbol, today):
            calls["n"] += 1
            return date(2026, 7, 10)

        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(earnings_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(earnings_mod, "_finnhub_next_earnings", fake_finnhub)

        await get_next_earnings(["AAPL"])
        await get_next_earnings(["AAPL"])
        assert calls["n"] == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_mock_mode_returns_future_dates(self, monkeypatch):
        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", True)
        result = await get_next_earnings(["AAPL", "TSLA"])
        assert set(result) == {"AAPL", "TSLA"}
        for d in result.values():
            assert d > date.today()

    @pytest.mark.asyncio
    async def test_yfinance_timeout_returns_none(self, monkeypatch):
        import time

        async def fake_finnhub(symbol, today):
            return None

        def slow_yf(symbol, today):
            time.sleep(30)
            return date(2026, 7, 15)

        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(earnings_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(earnings_mod, "_finnhub_next_earnings", fake_finnhub)
        monkeypatch.setattr(earnings_mod, "_yf_next_earnings", slow_yf)
        monkeypatch.setattr(earnings_mod, "_YF_TIMEOUT", 0.1)

        result = await get_next_earnings(["AAPL"])
        assert result["AAPL"] is None

    @pytest.mark.asyncio
    async def test_both_sources_fail_returns_none(self, monkeypatch):
        async def failing_finnhub(symbol, today):
            raise httpx.HTTPStatusError("403", request=None, response=None)

        def failing_yf(symbol, today):
            raise Exception("Yahoo blocked")

        monkeypatch.setattr(earnings_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(earnings_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(earnings_mod, "_finnhub_next_earnings", failing_finnhub)
        monkeypatch.setattr(earnings_mod, "_yf_next_earnings", failing_yf)

        result = await get_next_earnings(["AAPL"])
        assert result["AAPL"] is None

"""
Tests for the on-demand intraday 1-minute bars service.

Focus: the yfinance DataFrame → bar-dict parsing must be airtight (correct
ET timestamps, NaN minutes dropped), the 90s TTL cache must serve hits without
re-fetching, and every failure path must degrade to an empty list rather than
raise into the request handler.
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services import bars as bars_service

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    bars_service._cache.clear()
    # Ensure tests don't short-circuit via mock mode.
    monkeypatch.setattr(bars_service.settings, "scraper_mock_mode", False)
    yield
    bars_service._cache.clear()


def _df(rows):
    """Build a yfinance-shaped intraday frame: tz-aware index + Close column."""
    index = pd.DatetimeIndex([ts for ts, _ in rows])
    return pd.DataFrame({"Close": [c for _, c in rows]}, index=index)


class TestFetchIntradayParsing:
    def test_converts_to_et_iso(self, monkeypatch):
        # 14:30 UTC == 10:30 ET (EDT, summer).
        ts = datetime(2026, 6, 22, 14, 30, tzinfo=_UTC)
        monkeypatch.setattr(
            bars_service.yf, "Ticker",
            lambda s: type("T", (), {"history": lambda self, **k: _df([(ts, 24.5)])})(),
        )
        bars = bars_service._fetch_intraday("AAPL")
        assert len(bars) == 1
        assert bars[0]["close"] == 24.5
        # 10:30 ET regardless of source tz.
        assert datetime.fromisoformat(bars[0]["t"]).hour == 10
        assert datetime.fromisoformat(bars[0]["t"]).minute == 30

    def test_drops_nan_close(self, monkeypatch):
        t0 = datetime(2026, 6, 22, 13, 30, tzinfo=_UTC)
        t1 = datetime(2026, 6, 22, 13, 31, tzinfo=_UTC)
        t2 = datetime(2026, 6, 22, 13, 32, tzinfo=_UTC)
        monkeypatch.setattr(
            bars_service.yf, "Ticker",
            lambda s: type("T", (), {"history": lambda self, **k: _df([(t0, 10.0), (t1, float("nan")), (t2, 11.0)])})(),
        )
        bars = bars_service._fetch_intraday("AAPL")
        assert [b["close"] for b in bars] == [10.0, 11.0]

    def test_empty_frame_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            bars_service.yf, "Ticker",
            lambda s: type("T", (), {"history": lambda self, **k: pd.DataFrame()})(),
        )
        assert bars_service._fetch_intraday("THIN") == []

    def test_order_preserved_oldest_first(self, monkeypatch):
        t0 = datetime(2026, 6, 22, 13, 30, tzinfo=_UTC)
        t1 = datetime(2026, 6, 22, 13, 31, tzinfo=_UTC)
        monkeypatch.setattr(
            bars_service.yf, "Ticker",
            lambda s: type("T", (), {"history": lambda self, **k: _df([(t0, 10.0), (t1, 10.5)])})(),
        )
        bars = bars_service._fetch_intraday("AAPL")
        assert bars[0]["close"] == 10.0
        assert bars[1]["close"] == 10.5


@pytest.mark.asyncio
class TestGetIntradayBars:
    async def test_mock_mode_returns_empty(self, monkeypatch):
        monkeypatch.setattr(bars_service.settings, "scraper_mock_mode", True)
        # Should not call yfinance at all.
        monkeypatch.setattr(bars_service, "_fetch_intraday", lambda s: (_ for _ in ()).throw(AssertionError("called")))
        assert await bars_service.get_intraday_bars("AAPL") == []

    async def test_cache_hit_skips_fetch(self, monkeypatch):
        calls = {"n": 0}

        def fake(symbol):
            calls["n"] += 1
            return [{"t": "2026-06-22T10:30:00-04:00", "close": 1.0}]

        monkeypatch.setattr(bars_service, "_fetch_intraday", fake)
        first = await bars_service.get_intraday_bars("AAPL")
        second = await bars_service.get_intraday_bars("AAPL")
        assert first == second
        assert calls["n"] == 1  # second call served from cache

    async def test_stale_cache_refetches(self, monkeypatch):
        calls = {"n": 0}

        def fake(symbol):
            calls["n"] += 1
            return [{"t": "2026-06-22T10:30:00-04:00", "close": float(calls["n"])}]

        monkeypatch.setattr(bars_service, "_fetch_intraday", fake)
        await bars_service.get_intraday_bars("AAPL")
        # Expire the cached entry.
        ts, data = bars_service._cache["AAPL"]
        bars_service._cache["AAPL"] = (ts - bars_service._CACHE_TTL - 1, data)
        await bars_service.get_intraday_bars("AAPL")
        assert calls["n"] == 2

    async def test_failure_returns_empty(self, monkeypatch):
        def boom(symbol):
            raise RuntimeError("network down")

        monkeypatch.setattr(bars_service, "_fetch_intraday", boom)
        assert await bars_service.get_intraday_bars("AAPL") == []

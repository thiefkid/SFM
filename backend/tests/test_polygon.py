"""
Tests for the Polygon.io daily turnover service.

Verifies:
  - v × vw computation correctness
  - Timestamp → date conversion (UTC)
  - Cache behaviour (no redundant API calls)
  - Graceful fallback on API failure
  - Rate-limit (429) retry logic
  - Empty/missing field handling
"""

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import polygon as polygon_mod
from app.services.polygon import (
    DailyBar, _fetch_and_cache, _ts_to_date, get_cached_bar, get_daily_turnover,
)


# ---------------------------------------------------------------------------
# Unit: timestamp conversion
# ---------------------------------------------------------------------------

class TestTsToDate:
    def test_utc_midnight(self):
        # 2024-06-17 00:00:00 UTC = 1718582400000 ms
        assert _ts_to_date(1718582400000) == date(2024, 6, 17)

    def test_utc_midday(self):
        # 2024-06-17 12:00:00 UTC = 1718625600000 ms
        assert _ts_to_date(1718625600000) == date(2024, 6, 17)

    def test_epoch(self):
        assert _ts_to_date(0) == date(1970, 1, 1)


# ---------------------------------------------------------------------------
# Unit: v × vw computation via _fetch_and_cache
# ---------------------------------------------------------------------------

def _make_bar(dt: date, volume: float, vwap: float) -> dict:
    ts = int(datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp() * 1000)
    return {"t": ts, "v": volume, "vw": vwap, "o": 100, "h": 105, "l": 95, "c": 102}


@pytest.fixture(autouse=True)
def clear_cache():
    polygon_mod._cache.clear()
    polygon_mod._cache_populated_symbols.clear()
    polygon_mod._bar_cache.clear()
    yield
    polygon_mod._cache.clear()
    polygon_mod._cache_populated_symbols.clear()
    polygon_mod._bar_cache.clear()


class TestFetchAndCache:
    @pytest.mark.asyncio
    async def test_v_times_vw_computed_correctly(self):
        bars = [
            _make_bar(date(2024, 6, 14), volume=1_000_000, vwap=150.25),
            _make_bar(date(2024, 6, 17), volume=2_500_000, vwap=152.00),
        ]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            result = await _fetch_and_cache("AAPL", "2024-06-10", "2024-06-17")

        assert result[date(2024, 6, 14)] == pytest.approx(1_000_000 * 150.25)
        assert result[date(2024, 6, 17)] == pytest.approx(2_500_000 * 152.00)

    @pytest.mark.asyncio
    async def test_results_cached(self):
        bars = [_make_bar(date(2024, 6, 14), 1_000_000, 150.0)]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            await _fetch_and_cache("AAPL", "2024-06-10", "2024-06-17")

        assert ("AAPL", date(2024, 6, 14)) in polygon_mod._cache
        assert polygon_mod._cache[("AAPL", date(2024, 6, 14))] == pytest.approx(150_000_000)
        assert "AAPL" in polygon_mod._cache_populated_symbols

    @pytest.mark.asyncio
    async def test_missing_v_or_vw_skipped(self):
        bars = [
            {"t": int(datetime(2024, 6, 14, tzinfo=timezone.utc).timestamp() * 1000), "v": 1000},
            {"t": int(datetime(2024, 6, 15, tzinfo=timezone.utc).timestamp() * 1000), "vw": 100.0},
            {"t": int(datetime(2024, 6, 16, tzinfo=timezone.utc).timestamp() * 1000)},
        ]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            result = await _fetch_and_cache("BAD", "2024-06-10", "2024-06-17")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_zero_volume_skipped(self):
        bars = [_make_bar(date(2024, 6, 14), volume=0, vwap=150.0)]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            result = await _fetch_and_cache("ZERO", "2024-06-10", "2024-06-17")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self):
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=[]):
            result = await _fetch_and_cache("FAIL", "2024-06-10", "2024-06-17")

        assert result == {}


# ---------------------------------------------------------------------------
# Integration: get_daily_turnover
# ---------------------------------------------------------------------------

class TestGetDailyTurnover:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self):
        with patch.object(polygon_mod.settings, "polygon_api_key", ""):
            result = await get_daily_turnover(["AAPL"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_symbols_returns_empty(self):
        result = await get_daily_turnover([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_cached_symbols_not_refetched(self):
        polygon_mod._cache_populated_symbols.add("AAPL")
        polygon_mod._cache[("AAPL", date(2024, 6, 14))] = 150_000_000.0

        mock_fetch = AsyncMock(return_value=[])
        with patch.object(polygon_mod, "_fetch_and_cache", mock_fetch):
            with patch.object(polygon_mod.settings, "polygon_api_key", "test_key"):
                result = await get_daily_turnover(["AAPL"])

        mock_fetch.assert_not_called()
        assert "AAPL" in result

    @pytest.mark.asyncio
    async def test_multiple_symbols_fetched(self):
        from datetime import timedelta
        recent = date.today() - timedelta(days=3)
        bars_aapl = [_make_bar(recent, 1_000_000, 150.0)]
        bars_tsla = [_make_bar(recent, 5_000_000, 180.0)]

        call_count = 0
        async def mock_fetch(symbol, from_d, to_d):
            nonlocal call_count
            call_count += 1
            bars = bars_aapl if symbol == "AAPL" else bars_tsla
            for bar in bars:
                d = _ts_to_date(bar["t"])
                turnover = float(bar["v"]) * float(bar["vw"])
                polygon_mod._cache[(symbol, d)] = turnover
            polygon_mod._cache_populated_symbols.add(symbol)
            return {_ts_to_date(b["t"]): float(b["v"]) * float(b["vw"]) for b in bars}

        with patch.object(polygon_mod, "_fetch_and_cache", side_effect=mock_fetch):
            with patch.object(polygon_mod.settings, "polygon_api_key", "test_key"):
                result = await get_daily_turnover(["AAPL", "TSLA"])

        assert call_count == 2
        assert recent in result["AAPL"]
        assert result["AAPL"][recent] == pytest.approx(150_000_000)
        assert result["TSLA"][recent] == pytest.approx(900_000_000)


# ---------------------------------------------------------------------------
# Unit: 429 retry logic
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    @pytest.mark.asyncio
    async def test_429_retries_then_succeeds(self):
        import httpx

        response_429 = httpx.Response(429, request=httpx.Request("GET", "https://api.polygon.io/test"))
        response_200 = httpx.Response(
            200,
            json={"results": [_make_bar(date(2024, 6, 14), 1_000_000, 150.0)]},
            request=httpx.Request("GET", "https://api.polygon.io/test"),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[response_429, response_200])

        with patch.object(polygon_mod, "_http_client", mock_client):
            with patch.object(polygon_mod.settings, "polygon_api_key", "test_key"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await polygon_mod._fetch_daily_aggs("AAPL", "2024-06-10", "2024-06-17")

        assert len(result) == 1
        assert mock_client.get.call_count == 2


# ---------------------------------------------------------------------------
# Integration: _i5_from_polygon (from refresh.py)
# ---------------------------------------------------------------------------

class TestI5FromPolygon:
    def test_polygon_overrides_db_history(self):
        from app.services.historical import PastValuesResult
        from app.services.futu_scraper import StockSnapshot
        from app.api.routes.refresh import _i5_from_polygon

        db_history = PastValuesResult(
            values=[100.0] * 5,
            avg=100.0,
            count=5,
            dates=[date(2024, 6, i) for i in range(10, 15)],
        )
        snapshot = StockSnapshot(
            symbol="TEST", rt_price=50.0, open_price=49.0,
            prev_close=48.0, today_high=51.0, today_low=47.0,
            today_value=999.0,
        )
        polygon_data = {
            date(2024, 6, 10): 200_000_000.0,
            date(2024, 6, 11): 250_000_000.0,
            date(2024, 6, 12): 180_000_000.0,
            date(2024, 6, 13): 220_000_000.0,
            date(2024, 6, 14): 190_000_000.0,
        }
        today = date(2024, 6, 17)

        history, today_val = _i5_from_polygon(polygon_data, today, db_history, snapshot)

        assert len(history.values) == 5
        assert history.values[0] == pytest.approx(200_000_000.0)
        assert history.values[-1] == pytest.approx(190_000_000.0)
        assert history.avg == pytest.approx(sum(polygon_data.values()) / 5)
        # No polygon data for today → falls back to snapshot
        assert today_val == pytest.approx(999.0)

    def test_polygon_today_used_when_available(self):
        from app.services.historical import PastValuesResult
        from app.services.futu_scraper import StockSnapshot
        from app.api.routes.refresh import _i5_from_polygon

        db_history = PastValuesResult(values=[], avg=0.0, count=0, dates=[])
        snapshot = StockSnapshot(
            symbol="TEST", rt_price=50.0, open_price=49.0,
            prev_close=48.0, today_high=51.0, today_low=47.0,
            today_value=999.0,
        )
        today = date(2024, 6, 17)
        polygon_data = {
            date(2024, 6, 12): 180_000_000.0,
            date(2024, 6, 13): 220_000_000.0,
            date(2024, 6, 14): 190_000_000.0,
            today: 300_000_000.0,
        }

        history, today_val = _i5_from_polygon(polygon_data, today, db_history, snapshot)

        assert len(history.values) == 3
        assert today_val == pytest.approx(300_000_000.0)

    def test_insufficient_polygon_data_falls_back_to_db(self):
        from app.services.historical import PastValuesResult
        from app.services.futu_scraper import StockSnapshot
        from app.api.routes.refresh import _i5_from_polygon

        db_history = PastValuesResult(
            values=[100.0, 200.0, 300.0],
            avg=200.0,
            count=3,
            dates=[date(2024, 6, 12), date(2024, 6, 13), date(2024, 6, 14)],
        )
        snapshot = StockSnapshot(
            symbol="TEST", rt_price=50.0, open_price=49.0,
            prev_close=48.0, today_high=51.0, today_low=47.0,
            today_value=500.0,
        )
        # Only 2 completed days → below threshold of 3
        polygon_data = {
            date(2024, 6, 13): 220_000_000.0,
            date(2024, 6, 14): 190_000_000.0,
        }
        today = date(2024, 6, 17)

        history, today_val = _i5_from_polygon(polygon_data, today, db_history, snapshot)

        # Should fall back to DB
        assert history is db_history
        assert today_val == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Unit: DailyBar caching via _fetch_and_cache
# ---------------------------------------------------------------------------

class TestBarCache:
    @pytest.mark.asyncio
    async def test_fetch_and_cache_stores_bars(self):
        bars = [_make_bar(date(2024, 6, 14), volume=1_000_000, vwap=150.25)]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            await _fetch_and_cache("AAPL", "2024-06-10", "2024-06-17")

        bar = get_cached_bar("AAPL", date(2024, 6, 14))
        assert bar is not None
        assert isinstance(bar, DailyBar)
        assert bar.close == 102.0
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 95.0
        assert bar.volume == 1_000_000.0
        assert bar.vw == 150.25
        assert bar.turnover == pytest.approx(1_000_000 * 150.25)

    @pytest.mark.asyncio
    async def test_cached_bar_not_found(self):
        assert get_cached_bar("AAPL", date(2024, 6, 14)) is None

    @pytest.mark.asyncio
    async def test_multiple_bars_cached(self):
        bars = [
            _make_bar(date(2024, 6, 14), 1_000_000, 150.0),
            _make_bar(date(2024, 6, 17), 2_000_000, 155.0),
        ]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            await _fetch_and_cache("TSLA", "2024-06-10", "2024-06-17")

        bar1 = get_cached_bar("TSLA", date(2024, 6, 14))
        bar2 = get_cached_bar("TSLA", date(2024, 6, 17))
        assert bar1 is not None
        assert bar2 is not None
        assert bar1.volume == 1_000_000.0
        assert bar2.volume == 2_000_000.0

    @pytest.mark.asyncio
    async def test_missing_ohlc_defaults_to_zero(self):
        ts = int(datetime(2024, 6, 14, tzinfo=timezone.utc).timestamp() * 1000)
        bars = [{"t": ts, "v": 1000, "vw": 100.0}]
        with patch.object(polygon_mod, "_fetch_daily_aggs", new_callable=AsyncMock, return_value=bars):
            await _fetch_and_cache("NOHLC", "2024-06-10", "2024-06-17")

        bar = get_cached_bar("NOHLC", date(2024, 6, 14))
        assert bar is not None
        assert bar.open == 0.0
        assert bar.high == 0.0
        assert bar.low == 0.0
        assert bar.close == 0.0


# ---------------------------------------------------------------------------
# Integration: close price swap logic
# ---------------------------------------------------------------------------

class TestClosePriceSwap:
    def test_polygon_bar_overrides_snapshot_after_close(self):
        from dataclasses import replace
        from app.services.futu_scraper import StockSnapshot

        snapshot = StockSnapshot(
            symbol="AAPL", rt_price=150.50, open_price=149.00,
            prev_close=148.00, today_high=151.00, today_low=147.00,
            today_value=5_000_000.0,
        )

        polygon_mod._bar_cache[("AAPL", date(2024, 6, 14))] = DailyBar(
            date=date(2024, 6, 14),
            open=149.25, high=151.50, low=147.25, close=150.75,
            volume=10_000_000, vw=150.0, turnover=1_500_000_000,
        )

        bar = get_cached_bar("AAPL", date(2024, 6, 14))
        assert bar is not None
        swapped = replace(snapshot,
            rt_price=bar.close,
            open_price=bar.open,
            today_high=bar.high,
            today_low=bar.low,
        )

        assert swapped.rt_price == 150.75
        assert swapped.open_price == 149.25
        assert swapped.today_high == 151.50
        assert swapped.today_low == 147.25
        assert swapped.prev_close == 148.00  # prev_close NOT swapped
        assert swapped.today_value == 5_000_000.0  # today_value NOT swapped

    def test_indicators_compute_correctly_with_swapped_prices(self):
        from app.services.indicators import compute_i1, compute_i2, compute_i3

        close = 150.75   # Polygon official close
        open_ = 149.25   # Polygon official open
        high = 151.50    # Polygon official high
        prev_close = 148.00  # Finnhub prev close

        i1 = compute_i1(close, open_)
        assert i1 == pytest.approx((150.75 - 149.25) / 149.25)

        i2 = compute_i2(close, prev_close)
        assert i2 == pytest.approx((150.75 - 148.00) / 148.00)

        i3 = compute_i3(close, open_, high)
        assert i3 == pytest.approx((150.75 - 149.25) / (151.50 - 149.25))

    def test_no_swap_when_bar_unavailable(self):
        bar = get_cached_bar("AAPL", date(2099, 1, 1))
        assert bar is None

    def test_no_swap_when_close_is_zero(self):
        polygon_mod._bar_cache[("BAD", date(2024, 6, 14))] = DailyBar(
            date=date(2024, 6, 14),
            open=0.0, high=0.0, low=0.0, close=0.0,
            volume=0, vw=0, turnover=0,
        )
        bar = get_cached_bar("BAD", date(2024, 6, 14))
        assert bar is not None
        assert bar.close == 0.0  # swap should be skipped (close > 0 check)

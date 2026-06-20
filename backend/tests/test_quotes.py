"""
Tests for the live quote service snapshot builder.

Focus: the snapshot candle must stay valid (low <= price <= high) even when
Finnhub's high/low fields lag the last price, so downstream I3/ATH/52W are
computed on consistent data.
"""

import pytest

from app.services.quotes import _build_snapshot


def _quote(c, o, pc, h, l):
    return {"c": c, "o": o, "pc": pc, "h": h, "l": l}


class TestBuildSnapshot:
    def test_normal_quote_unchanged(self):
        snap = _build_snapshot("AAPL", _quote(c=12, o=10, pc=9, h=15, l=8), volume=1000)
        assert snap.rt_price == 12.0
        assert snap.open_price == 10.0
        assert snap.prev_close == 9.0
        assert snap.today_high == 15.0   # high already >= price
        assert snap.today_low == 8.0     # low already <= price
        assert snap.today_value == pytest.approx(12.0 * 1000)

    def test_stale_high_clamped_to_price(self):
        # Finnhub high (14) lags the last price (21) → high clamped up to 21,
        # so I3 can't exceed 1.0.
        snap = _build_snapshot("SPCX", _quote(c=21, o=10, pc=9, h=14, l=8), volume=500)
        assert snap.today_high == 21.0
        assert snap.rt_price == 21.0

    def test_stale_low_clamped_to_price(self):
        # Low (13) sits above the last price (11) → clamp down to 11.
        snap = _build_snapshot("XYZ", _quote(c=11, o=12, pc=13, h=15, l=13), volume=500)
        assert snap.today_low == 11.0

    def test_missing_high_falls_back_to_price(self):
        snap = _build_snapshot("NEW", _quote(c=20, o=18, pc=17, h=0, l=0), volume=100)
        assert snap.today_high == 20.0   # max(0, price)

    def test_missing_low_falls_back_to_price(self):
        snap = _build_snapshot("NEW", _quote(c=20, o=18, pc=17, h=22, l=0), volume=100)
        assert snap.today_low == 20.0    # raw_low == 0 → price

    def test_candle_invariant_holds(self):
        # low <= price <= high for an adversarial lagging feed.
        snap = _build_snapshot("LAG", _quote(c=50, o=40, pc=38, h=45, l=52), volume=10)
        assert snap.today_low <= snap.rt_price <= snap.today_high

    def test_empty_quote_returns_fallback(self):
        snap = _build_snapshot("DEAD", {"c": 0}, volume=100)
        assert snap.error is not None

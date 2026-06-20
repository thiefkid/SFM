"""
Tests for the indicator computation engine.

Focus: I3 (close position in the day's range) must never exceed 1.0, even when
the high feed lags the last price — a real condition on thin/recent tickers
(e.g. SPCX) that previously produced I3 > 1 and corrupted the signal.
"""

import pytest

from app.services.indicators import compute_i1, compute_i2, compute_i3


class TestComputeI1:
    def test_gain_from_open(self):
        assert compute_i1(110.0, 100.0) == pytest.approx(0.10)

    def test_loss_from_open(self):
        assert compute_i1(90.0, 100.0) == pytest.approx(-0.10)

    def test_zero_open_returns_none(self):
        assert compute_i1(100.0, 0.0) is None


class TestComputeI2:
    def test_gain_from_prev_close(self):
        assert compute_i2(105.0, 100.0) == pytest.approx(0.05)

    def test_zero_prev_close_returns_none(self):
        assert compute_i2(100.0, 0.0) is None


class TestComputeI3:
    def test_mid_range(self):
        # open=10, price=12, high=15 → (12-10)/(15-10) = 0.4
        assert compute_i3(12.0, 10.0, 15.0) == pytest.approx(0.4)

    def test_at_high_is_one(self):
        # price == high → exactly 1.0 (closed at the day's high)
        assert compute_i3(15.0, 10.0, 15.0) == pytest.approx(1.0)

    def test_at_open_returns_none(self):
        # high == open == price → no range above open
        assert compute_i3(10.0, 10.0, 10.0) is None

    def test_below_open_is_negative(self):
        # open=10, price=8, high=15 → (8-10)/(15-10) = -0.4
        assert compute_i3(8.0, 10.0, 15.0) == pytest.approx(-0.4)

    def test_stale_high_clamped_to_one(self):
        # THE BUG: high feed lags the last price. open=10, price=21, high=15
        # (stale). Raw (21-10)/(15-10) = 2.2 — but price IS the real high, so
        # the effective high is the price and I3 must be exactly 1.0.
        assert compute_i3(21.0, 10.0, 15.0) == pytest.approx(1.0)

    def test_spcx_like_never_exceeds_one(self):
        # Regression guard for the reported SPCX 2.1 reading.
        result = compute_i3(rt_price=21.0, open_price=10.0, today_high=15.0)
        assert result is not None
        assert result <= 1.0

    def test_price_exactly_at_lagged_high(self):
        # price == high but both above open → 1.0
        assert compute_i3(20.0, 12.0, 20.0) == pytest.approx(1.0)

    def test_degenerate_high_below_open_returns_none(self):
        # Broken data: high and price both at/below open → no positive range.
        # open=10, price=9, high=8 → effective high 9, denom -1 ≤ 0 → None
        # (defensible "unknown" rather than a spurious positive reading).
        assert compute_i3(9.0, 10.0, 8.0) is None

    def test_invariant_across_grid(self):
        # Exhaustive small grid: I3 is never > 1.0 for any input combination.
        for open_p in (1.0, 10.0, 50.0):
            for high in (0.0, 5.0, 10.0, 60.0):
                for price in (1.0, 10.0, 55.0, 100.0):
                    r = compute_i3(price, open_p, high)
                    if r is not None:
                        assert r <= 1.0 + 1e-9, f"I3>1 for o={open_p} h={high} p={price}: {r}"

"""Tests for the company-profile (market cap) service."""

import httpx
import pytest

from datetime import date, datetime, timezone

from app.services import profile as profile_mod
from app.services.profile import _parse_market_cap, get_market_caps


class TestParseMarketCap:
    def test_millions_to_absolute_usd(self):
        # Finnhub returns market cap in millions
        assert _parse_market_cap({"marketCapitalization": 2500}) == 2_500_000_000

    def test_float_value(self):
        assert _parse_market_cap({"marketCapitalization": 1234.5}) == 1_234_500_000

    def test_missing_key_returns_none(self):
        assert _parse_market_cap({}) is None

    def test_none_payload_returns_none(self):
        assert _parse_market_cap(None) is None

    def test_zero_returns_none(self):
        assert _parse_market_cap({"marketCapitalization": 0}) is None

    def test_negative_returns_none(self):
        assert _parse_market_cap({"marketCapitalization": -5}) is None

    def test_non_numeric_returns_none(self):
        assert _parse_market_cap({"marketCapitalization": "n/a"}) is None


class TestGetMarketCaps:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        profile_mod._cache.clear()
        yield
        profile_mod._cache.clear()

    @pytest.mark.asyncio
    async def test_empty_symbols(self):
        assert await get_market_caps([]) == {}

    @pytest.mark.asyncio
    async def test_fetches_and_returns(self, monkeypatch):
        async def fake_fetch(symbol):
            return 3_000_000_000.0

        monkeypatch.setattr(profile_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(profile_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(profile_mod, "_fetch_market_cap", fake_fetch)

        result = await get_market_caps(["AAPL"])
        assert result["AAPL"] == 3_000_000_000.0

    @pytest.mark.asyncio
    async def test_cached_within_same_day(self, monkeypatch):
        calls = {"n": 0}

        async def fake_fetch(symbol):
            calls["n"] += 1
            return 1_000_000_000.0

        monkeypatch.setattr(profile_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(profile_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(profile_mod, "_fetch_market_cap", fake_fetch)

        await get_market_caps(["AAPL"])
        await get_market_caps(["AAPL"])
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_none(self, monkeypatch):
        async def failing_fetch(symbol):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(profile_mod.settings, "scraper_mock_mode", False)
        monkeypatch.setattr(profile_mod.settings, "finnhub_api_key", "key")
        monkeypatch.setattr(profile_mod, "_fetch_market_cap", failing_fetch)

        result = await get_market_caps(["AAPL"])
        assert result["AAPL"] is None

    @pytest.mark.asyncio
    async def test_mock_mode_returns_positive(self, monkeypatch):
        monkeypatch.setattr(profile_mod.settings, "scraper_mock_mode", True)
        result = await get_market_caps(["AAPL", "TSLA"])
        assert set(result) == {"AAPL", "TSLA"}
        for v in result.values():
            assert v > 0

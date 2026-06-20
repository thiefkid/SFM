"""Tests for the on-demand company news service."""

import time

import httpx
import pytest

from app.services import news as news_mod
from app.services.news import get_company_news


class TestGetCompanyNews:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        news_mod._cache.clear()
        yield
        news_mod._cache.clear()

    @pytest.mark.asyncio
    async def test_returns_articles(self, monkeypatch):
        raw_response = [
            {
                "headline": "AAPL hits new high",
                "summary": "Apple stock surged today...",
                "source": "Reuters",
                "url": "https://example.com/1",
                "image": "https://example.com/img.jpg",
                "datetime": 1750000000,
                "category": "company",
            },
            {
                "headline": "AAPL earnings preview",
                "summary": "Analysts expect...",
                "source": "Bloomberg",
                "url": "https://example.com/2",
                "image": "",
                "datetime": 1749900000,
                "category": "company",
            },
        ]

        async def fake_get(url, params=None):
            class FakeResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return raw_response
            return FakeResp()

        monkeypatch.setattr(news_mod._http_client, "get", fake_get)
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "key")

        articles = await get_company_news("AAPL")
        assert len(articles) == 2
        assert articles[0]["headline"] == "AAPL hits new high"
        assert articles[1]["source"] == "Bloomberg"

    @pytest.mark.asyncio
    async def test_limits_to_count(self, monkeypatch):
        raw_response = [
            {"headline": f"Article {i}", "summary": "", "source": "", "url": "",
             "image": "", "datetime": 0, "category": ""}
            for i in range(10)
        ]

        async def fake_get(url, params=None):
            class FakeResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return raw_response
            return FakeResp()

        monkeypatch.setattr(news_mod._http_client, "get", fake_get)
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "key")

        articles = await get_company_news("AAPL", count=3)
        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_cached_within_ttl(self, monkeypatch):
        calls = {"n": 0}

        async def fake_get(url, params=None):
            calls["n"] += 1
            class FakeResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return [{"headline": "test", "summary": "", "source": "",
                                          "url": "", "image": "", "datetime": 0, "category": ""}]
            return FakeResp()

        monkeypatch.setattr(news_mod._http_client, "get", fake_get)
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "key")

        await get_company_news("AAPL")
        await get_company_news("AAPL")
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "")
        articles = await get_company_news("AAPL")
        assert articles == []

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self, monkeypatch):
        async def failing_get(url, params=None):
            raise httpx.ConnectError("timeout")

        monkeypatch.setattr(news_mod._http_client, "get", failing_get)
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "key")

        articles = await get_company_news("AAPL")
        assert articles == []

    @pytest.mark.asyncio
    async def test_unexpected_format_returns_empty(self, monkeypatch):
        async def fake_get(url, params=None):
            class FakeResp:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return {"error": "invalid symbol"}
            return FakeResp()

        monkeypatch.setattr(news_mod._http_client, "get", fake_get)
        monkeypatch.setattr(news_mod.settings, "finnhub_api_key", "key")

        articles = await get_company_news("AAPL")
        assert articles == []

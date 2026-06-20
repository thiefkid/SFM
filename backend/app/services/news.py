"""
On-demand company news per symbol via Finnhub /company-news.

Fetched only when a user expands the News section for a ticker, so rate
limiting is minimal (one symbol at a time, human-paced). Results are
cached for 5 minutes to avoid redundant calls on re-expand.
"""

import logging
import time
from datetime import date, timedelta

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_FINNHUB_NEWS = "https://finnhub.io/api/v1/company-news"
_http_client = httpx.AsyncClient(timeout=10.0)

_CACHE_TTL = 300  # 5 minutes
# symbol -> (fetched_at_monotonic, list[NewsItem dict])
_cache: dict[str, tuple[float, list[dict]]] = {}


async def get_company_news(symbol: str, count: int = 5) -> list[dict]:
    """Return up to `count` recent news items for a symbol.

    Each item: {headline, summary, source, url, image, datetime, category}.
    """
    now = time.monotonic()
    cached = _cache.get(symbol)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    if not settings.finnhub_api_key:
        logger.warning("News: no Finnhub API key configured")
        return []

    to_date = date.today()
    from_date = to_date - timedelta(days=14)

    try:
        r = await _http_client.get(
            _FINNHUB_NEWS,
            params={
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as exc:
        logger.warning("Finnhub news failed for %s: %s", symbol, exc)
        return []

    if not isinstance(raw, list):
        logger.warning("Finnhub news unexpected format for %s: %s", symbol, type(raw).__name__)
        return []

    items = []
    for article in raw[:count]:
        items.append({
            "headline": article.get("headline", ""),
            "summary": article.get("summary", ""),
            "source": article.get("source", ""),
            "url": article.get("url", ""),
            "image": article.get("image", ""),
            "datetime": article.get("datetime", 0),
            "category": article.get("category", ""),
        })

    _cache[symbol] = (now, items)
    logger.info("News %s: fetched %d items", symbol, len(items))
    return items

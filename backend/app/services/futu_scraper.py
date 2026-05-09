"""
Futu web scraper using Playwright.

Scrapes:
  1. Most-active US stocks page → top 10 symbols
  2. Individual stock pages    → RT price, open, prev close, today high, today value
  3. NASDAQ index page         → current level, open, prev close

NOTE: Futu is a JS-rendered SPA. Selectors may need updating if Futu changes
their frontend. If scraping fails, enable SCRAPER_MOCK_MODE=true in .env for
development with synthetic data.
"""

import asyncio
import re
from dataclasses import dataclass

from playwright.async_api import async_playwright, Page, Browser

from app.core.config import settings


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StockSnapshot:
    symbol: str
    rt_price: float
    open_price: float
    prev_close: float
    today_high: float
    today_low: float
    today_value: float          # turnover in USD (price × volume so far today)
    error: str | None = None    # set if scrape partially failed


@dataclass
class NasdaqSnapshot:
    rt_level: float
    open_level: float
    prev_close: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Mock data (used when SCRAPER_MOCK_MODE=true)
# ---------------------------------------------------------------------------

_MOCK_SYMBOLS = ["NVDA", "TSLA", "AAPL", "AMD", "AMZN", "META", "MSFT", "GOOGL", "SPY", "QQQ"]

_MOCK_STOCKS: dict[str, StockSnapshot] = {
    #                         rt      open    prev    high    low     turnover
    "NVDA":  StockSnapshot("NVDA",  875.40, 850.00, 860.20, 882.10, 840.00, 4_200_000_000),
    "TSLA":  StockSnapshot("TSLA",  245.30, 238.00, 241.50, 250.80, 235.00, 3_100_000_000),
    "AAPL":  StockSnapshot("AAPL",  189.75, 187.20, 188.90, 191.30, 186.50, 1_800_000_000),
    "AMD":   StockSnapshot("AMD",   162.50, 158.00, 160.30, 165.70, 156.80,   980_000_000),
    "AMZN":  StockSnapshot("AMZN",  183.20, 180.50, 181.80, 185.40, 179.60, 1_200_000_000),
    "META":  StockSnapshot("META",  492.10, 485.00, 488.60, 495.30, 483.20,   920_000_000),
    "MSFT":  StockSnapshot("MSFT",  415.80, 411.00, 413.40, 417.90, 410.20,   850_000_000),
    "GOOGL": StockSnapshot("GOOGL", 172.30, 169.50, 171.00, 174.20, 168.80,   760_000_000),
    "SPY":   StockSnapshot("SPY",   521.40, 518.00, 519.80, 523.10, 517.20, 2_500_000_000),
    "QQQ":   StockSnapshot("QQQ",   448.60, 444.00, 446.20, 451.30, 443.10, 1_900_000_000),
}

_MOCK_NASDAQ = NasdaqSnapshot(
    rt_level=17_845.20,
    open_level=17_700.00,
    prev_close=17_718.30,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_value(text: str) -> float | None:
    """Parse a price/value string like '$1.23B', '1,234.56', '2.3T' → float."""
    if not text:
        return None
    text = text.strip().replace(",", "").replace("$", "").replace("+", "")
    multiplier = 1.0
    if text.endswith("T"):
        multiplier = 1_000_000_000_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


async def _safe_text(page: Page, selector: str) -> str:
    """Return inner text of first matching element, or empty string."""
    try:
        el = await page.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

class FutuScraper:
    def __init__(self) -> None:
        self._browser: Browser | None = None

    async def _get_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(
                headless=settings.playwright_headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        return self._browser

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_top_active_symbols(self) -> list[str]:
        """Return top 10 most active US stock symbols from Futu."""
        if settings.scraper_mock_mode:
            return list(_MOCK_SYMBOLS)

        browser = await self._get_browser()
        page = await browser.new_page()
        try:
            await page.goto(settings.futu_most_active_url, timeout=settings.scraper_timeout_ms)
            # Wait for at least one stock link to appear (SPA content)
            try:
                await page.wait_for_selector("a[href*='/en/stock/']", timeout=settings.scraper_timeout_ms)
            except Exception:
                await page.wait_for_load_state("load", timeout=settings.scraper_timeout_ms)

            # Extract all links that look like /en/stock/XXXX-US
            links = await page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    return anchors
                        .map(a => a.getAttribute('href'))
                        .filter(href => href && /\\/en\\/stock\\/[A-Z]+-US/.test(href));
                }
            """)

            symbols: list[str] = []
            seen: set[str] = set()
            for href in links:
                match = re.search(r"/en/stock/([A-Z]+)-US", href)
                if match:
                    symbol = match.group(1)
                    if symbol not in seen:
                        seen.add(symbol)
                        symbols.append(symbol)
                if len(symbols) >= 10:
                    break

            return symbols if symbols else list(_MOCK_SYMBOLS)
        finally:
            await page.close()

    async def get_stock_snapshot(self, symbol: str) -> StockSnapshot:
        """Scrape a single stock page and return its snapshot."""
        if settings.scraper_mock_mode:
            return _MOCK_STOCKS.get(symbol, _make_fallback_snapshot(symbol))

        browser = await self._get_browser()
        page = await browser.new_page()
        try:
            url = settings.futu_stock_base_url.format(symbol=symbol)
            await page.goto(url, timeout=settings.scraper_timeout_ms)
            # Wait for the live price element to appear
            try:
                await page.wait_for_selector("[class*='price-current']", timeout=settings.scraper_timeout_ms)
            except Exception:
                await page.wait_for_load_state("load", timeout=settings.scraper_timeout_ms)

            # Futu stock page structure (verified May 2026):
            # Live price: <ul class="price-current"><li class="price direct-up/down">411.79</li>...</ul>
            # disc-price shows the regular-session close only; price-current inner .price is always live
            # Stats grid: each .card-item has [value_child, label_child]
            data: dict = await page.evaluate("""
                () => {
                    const result = {};

                    // RT price — inner .price child of price-current (live; includes after-hours)
                    const curr = document.querySelector('[class*="price-current"]');
                    if (curr) {
                        const inner = curr.querySelector('[class*="price"]');
                        result.rt_price = (inner || curr).textContent.trim().split('\\n')[0].trim();
                    }

                    // Stats grid: each .card-item has [value_child, label_child]
                    const labelMap = {
                        'Open':        'open',
                        'Prev Close':  'prev_close',
                        'Prev. Close': 'prev_close',
                        'Pre. Close':  'prev_close',
                        'High':        'high',
                        'Low':         'low',
                        'Turnover':    'turnover',
                    };
                    for (const el of document.querySelectorAll('.card-item')) {
                        const children = Array.from(el.children);
                        if (children.length >= 2) {
                            const label = children[children.length - 1].textContent.trim();
                            const value = children[0].textContent.trim();
                            const key = labelMap[label];
                            if (key && !result[key]) result[key] = value;
                        }
                    }
                    return result;
                }
            """)

            rt_price = _parse_value(data.get("rt_price", ""))
            open_price = _parse_value(data.get("open", ""))
            prev_close = _parse_value(data.get("prev_close", ""))
            today_high = _parse_value(data.get("high", ""))
            today_low = _parse_value(data.get("low", ""))
            today_value = _parse_value(data.get("turnover", ""))

            missing = [k for k, v in {
                "rt_price": rt_price, "open": open_price,
                "prev_close": prev_close, "high": today_high,
            }.items() if v is None]

            error = f"Could not parse: {missing}" if missing else None

            return StockSnapshot(
                symbol=symbol,
                rt_price=rt_price or 0.0,
                open_price=open_price or 0.0,
                prev_close=prev_close or 0.0,
                today_high=today_high or 0.0,
                today_low=today_low or 0.0,
                today_value=today_value or 0.0,
                error=error,
            )
        except Exception as exc:
            return StockSnapshot(
                symbol=symbol,
                rt_price=0.0, open_price=0.0, prev_close=0.0,
                today_high=0.0, today_low=0.0, today_value=0.0,
                error=str(exc),
            )
        finally:
            await page.close()

    async def get_all_snapshots(self, symbols: list[str]) -> list[StockSnapshot]:
        """Scrape all stock pages concurrently (max 5 at a time)."""
        semaphore = asyncio.Semaphore(settings.scraper_concurrency)

        async def _fetch(symbol: str) -> StockSnapshot:
            async with semaphore:
                return await self.get_stock_snapshot(symbol)

        return await asyncio.gather(*[_fetch(s) for s in symbols])

    async def get_nasdaq_snapshot(self) -> NasdaqSnapshot:
        """Scrape NASDAQ composite index data from Futu."""
        if settings.scraper_mock_mode:
            return _MOCK_NASDAQ

        browser = await self._get_browser()
        page = await browser.new_page()
        try:
            # Futu NASDAQ composite index page (correct URL: .IXIC-US not IXIC-US)
            url = "https://www.futunn.com/en/stock/.IXIC-US"
            await page.goto(url, timeout=settings.scraper_timeout_ms)
            try:
                await page.wait_for_selector("[class*='price-current']", timeout=settings.scraper_timeout_ms)
            except Exception:
                try:
                    await page.wait_for_selector(".card-item", timeout=settings.scraper_timeout_ms)
                except Exception:
                    await page.wait_for_load_state("load", timeout=settings.scraper_timeout_ms)
                    await page.wait_for_timeout(3000)

            # price-current container holds the live index level; card-items hold Open/Prev Close
            data: dict = await page.evaluate("""
                () => {
                    const result = {};
                    const labelMap = {
                        'Open':        'open',
                        'Prev Close':  'prev_close',
                        'Prev. Close': 'prev_close',
                        'Pre. Close':  'prev_close',
                    };
                    for (const el of document.querySelectorAll('.card-item')) {
                        const ch = Array.from(el.children);
                        if (ch.length >= 2) {
                            const label = ch[ch.length - 1].textContent.trim();
                            const value = ch[0].textContent.trim();
                            const key = labelMap[label];
                            if (key && !result[key]) result[key] = value;
                        }
                    }
                    // RT level — price-current element (Futu index pages, verified May 2026)
                    const curr = document.querySelector('[class*="price-current"]');
                    if (curr) {
                        // Inner .price child has just the number; fallback to first line of text
                        const inner = curr.querySelector('[class*="price"]');
                        const raw = (inner || curr).textContent.trim();
                        result.rt_level = raw.split('\\n')[0].trim();
                    }
                    return result;
                }
            """)

            return NasdaqSnapshot(
                rt_level=_parse_value(data.get("rt_level", "")) or 0.0,
                open_level=_parse_value(data.get("open", "")) or 0.0,
                prev_close=_parse_value(data.get("prev_close", "")) or 0.0,
            )
        except Exception as exc:
            return NasdaqSnapshot(rt_level=0.0, open_level=0.0, prev_close=0.0, error=str(exc))
        finally:
            await page.close()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

scraper = FutuScraper()


def _make_fallback_snapshot(symbol: str) -> StockSnapshot:
    return StockSnapshot(
        symbol=symbol,
        rt_price=0.0, open_price=0.0, prev_close=0.0,
        today_high=0.0, today_low=0.0, today_value=0.0,
        error="No mock data available for symbol",
    )

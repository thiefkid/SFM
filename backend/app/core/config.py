from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://sfm:sfm@localhost:5432/sfm"

    # Futu most-active URL
    futu_most_active_url: str = (
        "https://www.futunn.com/en/quote/us/most-active-stocks"
    )
    futu_stock_base_url: str = "https://www.futunn.com/en/stock/{symbol}-US"

    # Scraper settings
    playwright_headless: bool = True
    scraper_concurrency: int = 5          # max parallel stock pages
    scraper_timeout_ms: int = 30_000      # per-page timeout
    scraper_mock_mode: bool = False       # set True for local dev without Futu access

    # CORS — comma-separated list of allowed origins, or * for all
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Scheduler — nightly price update (24h clock, ET)
    nightly_update_hour: int = 18
    nightly_update_minute: int = 0


settings = Settings()

# Project Memory

## Critical Instruction
This is a very important trading application that directly has PNL impact on trading. All data handling and logic MUST BE AIRTIGHT. No guessing and needs to have stringent tests to prove it works.

## Standing Instructions
- Always merge and push to main. Develop on feature branches but work goes to `main`.
- Do NOT paste service account JSON keys. Use short-lived tokens or log-paste instead.
- Backend URL: `https://sfm-backend-q2v3e4evxq-uc.a.run.app`

## Architecture
- **Backend**: FastAPI on Cloud Run (scale-to-zero compatible)
- **Frontend**: Next.js
- **Database**: Neon Postgres (daily prices, last refresh persistence, distributed lock)
- **Data sources**: Finnhub (realtime quotes), Polygon.io (authoritative daily turnover), yfinance (volume, NASDAQ), Futu scraper (Heat List ranking)
- **Refresh**: Backend-driven via GCP Cloud Scheduler (every 2 min, 3:40-4:00 PM ET weekdays). SSE push to frontend. Single-flight distributed DB lock.
- **Turnover**: Historical days → Polygon.io daily v × vw (tape-derived, authoritative, EOD-only on free tier). Today → Finnhub price × yfinance volume (Polygon free tier has no intraday). Cached per process.

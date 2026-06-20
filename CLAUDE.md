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
- **Data sources**: Finnhub (realtime quotes), yfinance (volume, NASDAQ, intraday turnover), Futu scraper (Heat List ranking)
- **Refresh**: Backend-driven via GCP Cloud Scheduler (every 2 min, 3:40-4:00 PM ET weekdays). SSE push to frontend. Single-flight distributed DB lock.
- **Turnover**: Bar-aggregated VWAP from 15m intraday bars: Σ((H+L+C)/3 × bar_volume). Fallback to close×volume.

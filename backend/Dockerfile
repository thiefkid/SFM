FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-dev

RUN uv run playwright install chromium --with-deps

COPY . .

# Version info injected at build time (see .github/workflows/deploy-backend.yml).
ARG GIT_COMMIT=dev
ARG GIT_COMMIT_TIME=""
ENV GIT_COMMIT=$GIT_COMMIT
ENV GIT_COMMIT_TIME=$GIT_COMMIT_TIME

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

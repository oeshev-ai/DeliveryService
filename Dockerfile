# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
RUN pip install .

COPY tests ./tests
COPY webapp ./webapp

# Default: API (переопределяется в compose)
CMD ["uvicorn", "delivery_bot.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM base AS deps
COPY pyproject.toml .
RUN pip install -e ".[prod]"

# ── Development (hot reload, test tools) ──────────────────────────────────────
FROM deps AS development
RUN pip install -e ".[dev]"
COPY . .
EXPOSE 8000

# ── Production ────────────────────────────────────────────────────────────────
FROM deps AS production
COPY . .
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers"]

# ============================================================
# Stage 1: Builder — install production dependencies with uv
# ============================================================
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy only dependency manifests for layer caching
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev group) into a virtual env
RUN uv sync --no-dev --frozen --no-install-project

# Copy application source
COPY app/ ./app/
COPY main.py ./
COPY alembic/ ./alembic/
COPY alembic.ini ./

# ============================================================
# Stage 2: Runtime — minimal rootless image
# ============================================================
FROM python:3.12-slim AS runtime

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy virtual env and application from builder
COPY --from=builder --chown=appuser:appuser /build/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /build/app /app/app
COPY --from=builder --chown=appuser:appuser /build/main.py /app/main.py
COPY --from=builder --chown=appuser:appuser /build/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /build/alembic.ini /app/alembic.ini

# Create data directory for SQLite persistence
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

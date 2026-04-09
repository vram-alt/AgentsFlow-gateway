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

# Copy seed database (if exists) for initial deployment
COPY data/ ./data-seed/

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

# Copy seed database to a separate directory (not the volume mount point)
COPY --from=builder --chown=appuser:appuser /build/data-seed/ /app/data-seed/

# Create data directory for SQLite persistence (will be mounted as volume)
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Copy entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /app/docker-entrypoint.sh
# Normalize line endings for Windows checkouts so the script can be executed in Linux containers
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

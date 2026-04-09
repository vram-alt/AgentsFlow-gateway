#!/bin/sh
set -e

# Ensure venv is on PATH (sh doesn't inherit Dockerfile ENV in all cases)
export PATH="/app/.venv/bin:$PATH"

# ── Seed database initialization ─────────────────────────────────────
# On first run, the Docker volume at /app/data/ is empty.
# Copy the seed database from /app/data-seed/ if it exists and
# /app/data/gateway.db does not yet exist.
if [ -f /app/data-seed/gateway.db ] && [ ! -f /app/data/gateway.db ]; then
    echo "📦 Initializing database from seed..."
    cp /app/data-seed/gateway.db /app/data/gateway.db
    echo "✅ Seed database copied to /app/data/gateway.db"
fi

# ── Run Alembic migrations ───────────────────────────────────────────
# This Docker setup ships with a pre-seeded SQLite database. If the DB file is
# already present, mark it as current instead of replaying the initial migration.
if [ -f /app/data/gateway.db ]; then
    echo "🪪 SQLite database detected; stamping Alembic head..."
    python -m alembic stamp head
else
    echo "🔄 Running database migrations..."
    python -m alembic upgrade head
fi

echo "✅ Migrations complete"

# ── Start the application ────────────────────────────────────────────
exec "$@"

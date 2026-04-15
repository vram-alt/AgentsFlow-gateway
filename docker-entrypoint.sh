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
# Always run upgrade head — Alembic is idempotent and will only apply
# pending migrations.  This keeps existing data safe while applying
# any schema changes introduced by a new deployment.
if [ -f /app/data/gateway.db ]; then
    echo "🔄 Existing database detected; applying pending migrations..."
    python -m alembic upgrade head
else
    echo "🔄 No database found; running full migration..."
    python -m alembic upgrade head
fi

echo "✅ Migrations complete"

# ── Start the application ────────────────────────────────────────────
exec "$@"

#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# AI Gateway — Deploy Script
# ══════════════════════════════════════════════════════════════════════
# Usage:
#   ./deploy.sh              — build and start all services
#   ./deploy.sh build        — build images only
#   ./deploy.sh up           — start services (assumes images exist)
#   ./deploy.sh down         — stop all services
#   ./deploy.sh logs         — tail logs from all services
#   ./deploy.sh restart      — restart all services
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Check prerequisites ──────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    echo "❌ Docker Compose V2 is not available. Please update Docker."
    exit 1
fi

# ── Check .env exists ────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.production template..."
    cp .env.production .env
    echo "📝 Please edit .env with your production values before deploying!"
    echo "   Required changes:"
    echo "   - ADMIN_PASSWORD (change from default)"
    echo "   - WEBHOOK_SECRET (change from default)"
    echo "   - ENCRYPTION_KEY (generate new Fernet key)"
    echo "   - NEXT_PUBLIC_API_URL (set to your server's public URL)"
    echo "   - CORS_ORIGINS (set to your frontend's public URL)"
    exit 1
fi

# ── Validate critical env vars ───────────────────────────────────────
source .env 2>/dev/null || true

if [[ "${ADMIN_PASSWORD:-}" == *"CHANGE_ME"* ]]; then
    echo "❌ ADMIN_PASSWORD still contains default value. Please update .env"
    exit 1
fi

if [[ "${WEBHOOK_SECRET:-}" == *"CHANGE_ME"* ]]; then
    echo "❌ WEBHOOK_SECRET still contains default value. Please update .env"
    exit 1
fi

if [[ "${ENCRYPTION_KEY:-}" == *"CHANGE_ME"* ]]; then
    echo "❌ ENCRYPTION_KEY still contains default value. Please update .env"
    echo "   Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    exit 1
fi

# ── Commands ─────────────────────────────────────────────────────────
ACTION="${1:-deploy}"

case "$ACTION" in
    build)
        echo "🔨 Building Docker images..."
        docker compose build --no-cache
        echo "✅ Images built successfully"
        ;;
    up)
        echo "🚀 Starting services..."
        docker compose up -d
        echo "✅ Services started"
        echo "   Frontend: http://localhost:${FRONTEND_PORT:-3000}"
        echo "   Backend:  http://localhost:${BACKEND_PORT:-8000}"
        ;;
    down)
        echo "🛑 Stopping services..."
        docker compose down
        echo "✅ Services stopped"
        ;;
    logs)
        docker compose logs -f --tail=100
        ;;
    restart)
        echo "🔄 Restarting services..."
        docker compose down
        docker compose up -d
        echo "✅ Services restarted"
        ;;
    deploy|"")
        echo "🚀 Full deployment: build + start..."
        docker compose build
        docker compose up -d
        echo ""
        echo "✅ Deployment complete!"
        echo "   Frontend: http://localhost:${FRONTEND_PORT:-3000}"
        echo "   Backend:  http://localhost:${BACKEND_PORT:-8000}"
        echo "   Health:   http://localhost:${BACKEND_PORT:-8000}/health"
        ;;
    *)
        echo "Usage: $0 {build|up|down|logs|restart|deploy}"
        exit 1
        ;;
esac

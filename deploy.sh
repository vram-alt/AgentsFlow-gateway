#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# AI Gateway — Local Dev Helper
# ══════════════════════════════════════════════════════════════════════
# Production deployments are handled automatically by GitHub Actions
# when code is merged to main. See .github/workflows/deploy.yml
#
# This script is for LOCAL DEVELOPMENT only:
#   ./deploy.sh              — build and start all services
#   ./deploy.sh build        — build images only
#   ./deploy.sh up           — start services (assumes images exist)
#   ./deploy.sh down         — stop all services
#   ./deploy.sh logs         — tail logs from all services
#   ./deploy.sh restart      — restart all services
#   ./deploy.sh backup       — backup the database
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
    if [ -f .env.production ]; then
        echo "⚠️  .env file not found. Copying from .env.production template..."
        cp .env.production .env
        echo "📝 Please edit .env with your values."
    else
        echo "❌ No .env or .env.production file found."
        exit 1
    fi
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
    backup)
        echo "💾 Backing up database..."
        BACKUP_FILE="gateway_backup_$(date +%Y%m%d_%H%M%S).db"
        docker cp ai-gateway-backend:/app/data/gateway.db "./${BACKUP_FILE}"
        echo "✅ Database backed up to ${BACKUP_FILE}"
        ;;
    *)
        echo "Usage: $0 {build|up|down|logs|restart|deploy|backup}"
        exit 1
        ;;
esac

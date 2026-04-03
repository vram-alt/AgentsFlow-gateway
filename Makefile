.PHONY: test test-cov build publish up down logs migrate-create migrate-apply

IMAGE_NAME ?= ai-gateway-poc
IMAGE_TAG  ?= latest
REGISTRY   ?= ghcr.io/your-org

# ── Testing ──────────────────────────────────────────────
test:
	uv run pytest -x -q

test-cov:
	uv run pytest --cov=app --cov-report=term-missing -q

# ── Docker Build & Publish ───────────────────────────────
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

publish: build
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# ── Docker Compose Orchestration ─────────────────────────
up:
	IMAGE_NAME=$(IMAGE_NAME):$(IMAGE_TAG) docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ── Alembic Migrations ───────────────────────────────────
migrate-create:
	uv run alembic revision --autogenerate -m "$(msg)"

migrate-apply:
	uv run alembic upgrade head

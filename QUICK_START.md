# AI Gateway — Quick Start Guide

## What is it?
An intelligent proxy between your app and LLM providers (via Portkey). Adds guardrails, logging, and a management UI.

## Setup (2 min)

```bash
cp .env.example .env
# Edit .env → set ADMIN_USERNAME, ADMIN_PASSWORD, ENCRYPTION_KEY, WEBHOOK_SECRET
# Generate Fernet key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up -d
```

- **Backend**: `http://localhost:8000`
- **Frontend UI**: `http://localhost:3000`
- **Health check**: `GET /health`

## Auth
All API calls require **HTTP Basic Auth** (`ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`).

## Core Workflow

### 1. Add a Provider
`POST /api/providers/` → `{ "name": "portkey", "api_key": "pk-...", "base_url": "https://api.portkey.ai" }`

### 2. Create Guardrail Policies (optional)
`POST /api/policies/` → `{ "name": "no-pii", "body": "...", "provider_name": "portkey" }`

### 3. Send a Chat Message
```
POST /api/chat/send
{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "Hello"}],
  "provider_name": "portkey",
  "guardrail_ids": ["no-pii"]
}
```
Returns: `{ "trace_id", "content", "model", "usage", "guardrail_blocked" }`

### 4. View Logs & Stats
- `GET /api/logs/` — request history (filterable)
- `GET /api/stats/summary` — dashboard metrics
- `GET /api/stats/charts` — chart data

## Key Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/chat/send` | Send prompt to LLM |
| GET/POST/PUT/DELETE | `/api/providers/` | Manage LLM providers |
| GET/POST/PUT/DELETE | `/api/policies/` | Manage guardrails |
| PATCH | `/api/providers/{id}/toggle` | Enable/disable provider |
| PATCH | `/api/policies/{id}/toggle` | Enable/disable policy |
| POST | `/api/policies/sync` | Sync policies from cloud |
| GET | `/api/logs/` | View request logs |
| GET | `/api/stats/summary` | Aggregated stats |
| POST | `/api/tester/proxy` | Test sandbox |
| POST | `/api/webhook/report` | Incoming webhook (uses `X-Webhook-Secret` header) |

## Demo Mode
Set `DEMO_MODE=true` in `.env` to get simulated responses without a real LLM API key.

## Docs
Interactive Swagger: `http://localhost:8000/docs`

# AI Gateway Adapter — Phase 3 POC

A lightweight asynchronous API gateway with a web interface.  
Role: intelligent proxy between business logic and LLM providers (Portkey).

## Architecture

The project follows **Clean Architecture** principles with the **Adapter** pattern:

```
app/
├── domain/            # Pure entities, DTOs, contracts (zero external dependencies)
├── services/          # Use Cases — business logic orchestration
├── infrastructure/    # Database (SQLAlchemy Async), HTTP adapters (Portkey)
├── api/               # FastAPI routers, middleware, DI
```

## Quick Start

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Tech Stack

| Component       | Technology                        |
|-----------------|-----------------------------------|
| Backend         | FastAPI + Uvicorn                 |
| HTTP Client     | httpx (async)                     |
| Database        | SQLite (WAL) → PostgreSQL-ready   |
| ORM             | SQLAlchemy Async + aiosqlite      |
| Validation      | Pydantic V2                       |

## Known Limitations (POC)

### [RED-2] In-memory Rate Limiter — does not work in multi-worker deployments

The current rate limiter implementation for brute-force protection uses an
in-memory `dict` within each process. In multi-worker deployments
(e.g., `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`) each worker
maintains its own independent counter of failed attempts.

**Impact:** an attacker can distribute attempts across workers and
bypass the limit (instead of 5 attempts, they get `5 × N_workers`).

**Production recommendation:** replace with a Redis-backed sliding window
rate limiter (e.g., via `redis-py` + Lua script or the
`fastapi-limiter` library).

For the current POC with a single worker (`uvicorn --workers 1`) this limitation
is not critical.

## License

Proprietary — Phase 3 POC.

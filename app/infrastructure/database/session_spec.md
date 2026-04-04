# Specification: Database Connection Management (session.py)

> **Implementation file:** `session.py`
> **Layer:** Infrastructure (external world — I/O)
> **Responsibility:** Creating and configuring the async SQLAlchemy engine and session factory

---

## 1. General Rules

- All DB operations are **asynchronous** (via AsyncSession).
- Driver: aiosqlite for SQLite, switchable to PostgreSQL via DATABASE_URL.
- Mandatory WAL mode enablement during SQLite initialization.
- SQLAlchemy ORM models are **not exported** beyond the infrastructure layer.

---

## 2. Engine

- Created via the SQLAlchemy async engine factory with the DATABASE_URL parameter.
- Parameters: echo=False (in production), pool_pre_ping=True.
- **Connection pool parameters (mandatory):** pool size — 5 connections, maximum overflow — 10 additional connections beyond the pool size. These values should be externalized to application configuration for tuning under load. Explicit pool limits prevent exhaustion of file descriptors and DB limits under peak load.

---

## 3. WAL Mode for SQLite

- On each new connection to the SQLite engine, the system must automatically execute two SQL commands:
  - Enable WAL journal mode (journal_mode=WAL).
  - Set the lock wait timeout to 5000 ms (busy_timeout=5000).
- Mechanism: subscribe to the connection establishment event at the synchronous engine level.

---

## 4. Session Factory (SessionLocal)

- Async session factory bound to the engine.
- Parameters: use the async session class, disable automatic object expiration after commit (expire_on_commit=False).

---

## 5. Function: get_db_session

### Purpose

Async generator for FastAPI Depends. Returns an AsyncSession.

### Step-by-Step Logic

1. Open a session via the factory.
2. Yield the session to the calling code.
3. In the finally block, close the session.
4. On exception — perform a rollback before closing.

---

## 6. Database Schema Management

This module **does not manage** table creation or modification.
All responsibility for database schema management (table creation, migrations, rollbacks) is fully delegated to the Alembic migration system.

Detailed architectural rules are described in [`alembic_spec.md`](app/infrastructure/database/alembic_spec.md).

### Prohibited

- Calling the bulk table creation mechanism via the declarative base class metadata (create_all) from application code.
- Any imperative DDL schema changes at runtime.

### Permitted

- Exporting the engine object for use by Alembic in the migration configuration file.

---

## 7. Error Handling

| Scenario                        | Action                                      |
|---------------------------------|---------------------------------------------|
| SQLAlchemy connection error     | Logging + retry                             |
| Invalid DATABASE_URL            | ValueError at application startup           |
| DB connection error             | OperationalError → logging + re-raise       |

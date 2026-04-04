# Specification: Database Migration System (Alembic)

> **Layer:** Infrastructure (external world — I/O)  
> **Responsibility:** Versioning and evolution of the database DDL schema via managed migrations  
> **Related specifications:** [`session_spec.md`](app/infrastructure/database/session_spec.md), [`models_spec.md`](app/infrastructure/database/models_spec.md)

---

## 1. General Rules

- Database schema management is performed **exclusively** via Alembic. Direct table creation or modification from application code is prohibited.
- Each schema change (adding a table, column, index, constraint) is formalized as a separate migration with a unique revision.
- Migrations must be **idempotent**: repeated application must not cause an error.
- Each migration must contain both a forward application (upgrade) and a rollback (downgrade).

---

## 2. File and Directory Structure

### 2.1. Configuration File

- The Alembic configuration file is located at the **project root** (at the same level as requirements.txt).
- Contains the path to the migrations directory, the DB connection string, and a reference to the migration environment file.
- The DB connection string must be read from the DATABASE_URL environment variable, not hardcoded.

### 2.2. Migrations Directory

- All migration files are stored in the `app/infrastructure/database/migrations` directory.
- Inside the migrations directory:
  - Migration environment file (env.py) — entry point for Alembic.
  - Template for generating new revisions (script.py.mako).
  - `versions/` subdirectory — contains individual migration files.

---

## 3. Async Operation Mode

- Alembic must operate in **async mode**, using the SQLAlchemy async engine.
- The migration environment file (env.py) must:
  1. Create an async engine based on DATABASE_URL.
  2. Run migrations within an async connection context.
  3. Properly close the engine after migrations complete.
- For offline mode (SQL generation without DB connection), synchronous operation with the URL directly is acceptable.

---

## 4. Migration Autogeneration

- The migration environment file must import the declarative base class (Base) from the models module (`app/infrastructure/database/models.py`).
- The metadata of this base class is passed to Alembic as target_metadata for comparing the current DB state with the model definitions.
- This enables the autogeneration mode (--autogenerate flag), where Alembic automatically determines the difference between models and the current DB schema.

---

## 5. Model Imports

- Before passing metadata to Alembic, ensure that **all** ORM models are imported and registered in the declarative base class registry.
- The migration environment file must explicitly import the models module to guarantee registration of all tables in the metadata.
- When adding new models to the project, they must be accessible through the single models module — no additional edits to env.py are required.

---

## 6. Migration Naming Conventions

- Each migration must have a meaningful description in English (passed via the -m flag during generation).
- Description format: brief action + object (e.g., "add users table", "add index on logs created_at").
- Empty migrations (no changes in upgrade/downgrade) are not permitted in the repository.

---

## 7. Constraint Naming Conventions

- For cross-platform compatibility (SQLite, PostgreSQL) and correct autogeneration of migrations, the declarative base class must use an explicit constraint naming convention.
- Naming rules must cover: indexes, unique constraints, check constraints, foreign keys, and primary keys.
- This requirement is implemented at the models level (see [`models_spec.md`](app/infrastructure/database/models_spec.md)), but is critical for correct Alembic operation.

---

## 8. Integration with Application Lifecycle

- Alembic is **not invoked** automatically at application startup (FastAPI lifespan).
- Migrations are applied **manually** by the operator or via CI/CD pipeline before deployment.
- The application at startup must assume that the DB schema is already up to date.

---

## 9. Error Handling

| Scenario | Action |
|---|---|
| Incompatible revision (head conflict) | Manual resolution via merge revision |
| DB connection error during migration | Alembic exits with non-zero return code; operator analyzes the log |
| Rollback impossible (irreversible operation) | The downgrade function must explicitly raise an exception with explanation |
| Model-schema desynchronization | Detected via autogeneration; an empty migration signals no discrepancies |

---

## 10. Security

- The DB connection string is never stored in the Alembic configuration file in plain text. Environment variable substitution is used.
- Migration files (versions/ directory) are committed to version control. The Alembic configuration file is also committed, but without secrets.
- Local databases (SQLite files) are excluded from version control via .gitignore.

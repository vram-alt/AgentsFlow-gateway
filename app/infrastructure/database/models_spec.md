# Specification: SQLAlchemy ORM Models (models.py)

> **Implementation file:** `models.py`  
> **Layer:** Infrastructure (external world — I/O)  
> **Responsibility:** Defining database tables via declarative SQLAlchemy 2.0 ORM models

---

## 1. General Rules

- All DB operations are **asynchronous** (via AsyncSession).
- SQLAlchemy ORM models are **not exported** beyond the infrastructure layer.
- All models inherit from a single declarative base class (SQLAlchemy 2.0+ style).

---

## 2. Base Class

- A single declarative base class for all ORM models (SQLAlchemy 2.0+ style).
- All models inherit from this base class.

---

## 3. Table: ProviderModel

**Table name:** `providers`

| Column       | SQLAlchemy Type        | Constraints                    | Description                     |
|--------------|------------------------|--------------------------------|---------------------------------|
| `id`         | `Integer`              | PK, autoincrement              | Primary key                     |
| `name`       | `String(100)`          | NOT NULL, UNIQUE               | Provider name                   |
| `api_key`    | `String(500)`          | NOT NULL                       | API key (encrypted)             |
| `base_url`   | `String(500)`          | NOT NULL                       | Base API URL                    |
| `is_active`  | `Boolean`              | NOT NULL, default=True         | Activity flag (Soft Delete)     |
| `created_at` | `DateTime`             | NOT NULL, default=utcnow       | Creation date                   |
| `updated_at` | `DateTime`             | NOT NULL, default=utcnow, onupdate=utcnow | Update date       |

**api_key column encryption:** The api_key column value must be stored in encrypted form using symmetric encryption (Fernet algorithm). The master encryption key is read from the encryption_key field of the Settings class (ENCRYPTION_KEY environment variable, defined in config_spec.md). Mechanism for obtaining the key in the ORM layer: import the get_settings function from the configuration module. On DB write — the value is encrypted; on DB read — it is decrypted. This prevents disclosure of all provider API keys if the DB file (SQLite) is compromised or via SQL injection.

**Relationships:** policies → relationship to PolicyModel (one-to-many).

---

## 4. Table: PolicyModel

**Table name:** `policies`

| Column        | SQLAlchemy Type        | Constraints                    | Description                     |
|---------------|------------------------|--------------------------------|---------------------------------|
| `id`          | `Integer`              | PK, autoincrement              | Primary key                     |
| `name`        | `String(200)`          | NOT NULL                       | Policy name                     |
| `body`        | `Text`                 | NOT NULL                       | JSON rule body (serialized dict)|
| `remote_id`   | `String(200)`          | NULLABLE, UNIQUE               | Vendor-side policy ID           |
| `provider_id` | `Integer`              | FK → providers.id, ON DELETE SET NULL | Provider association     |
| `is_active`   | `Boolean`              | NOT NULL, default=True         | Activity flag (Soft Delete)     |
| `created_at`  | `DateTime`             | NOT NULL, default=utcnow       | Creation date                   |
| `updated_at`  | `DateTime`             | NOT NULL, default=utcnow, onupdate=utcnow | Update date       |

**Note:** The body field is stored as Text (JSON string). When migrating to PostgreSQL, it should be replaced with JSONB.

---

## 5. Table: LogEntryModel

**Table name:** `logs`

| Column       | SQLAlchemy Type        | Constraints                    | Description                     |
|--------------|------------------------|--------------------------------|---------------------------------|
| `id`         | `Integer`              | PK, autoincrement              | Primary key                     |
| `trace_id`   | `String(36)`           | NOT NULL, INDEX                | Correlation UUID                |
| `event_type` | `String(50)`           | NOT NULL                       | Event type (Enum as string)     |
| `payload`    | `Text`                 | NOT NULL                       | Polymorphic body (JSON string)  |
| `created_at` | `DateTime`             | NOT NULL, default=utcnow       | Creation date                   |

**Indexes:** ix_logs_trace_id on the trace_id column for fast correlation ID lookups.

---

## 6. Error Handling

| Scenario                        | Action                                      |
|---------------------------------|---------------------------------------------|
| UNIQUE field duplicate          | IntegrityError → propagated to service      |
| Invalid JSON on serialization   | ValueError → propagated to service          |

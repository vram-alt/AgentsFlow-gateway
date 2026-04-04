# Specification: Domain Entity Policy (policy.py)

> **Implementation file:** `policy.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Describing the "Security Policy" (Guardrail) business entity

---

## 1. General Rules

- The model inherits from BaseModel (Pydantic).
- Uses Pydantic V2 (configuration via ConfigDict).
- Date fields have type datetime. The default value is set via a factory mechanism (default_factory) that retrieves the current UTC time **on each instance creation**, not once at module import. Use the timezone-aware variant for obtaining the current time (with explicit UTC timezone), as the timezone-naive variant is deprecated starting with Python 3.12.
- Boolean activity flags default to True.
- The model **does not contain** database logic — it is a pure domain object.

---

## 2. Entity: Policy

### Purpose

Stores security rules (Guardrails) that are synchronized with the provider's cloud.

### Fields

| Field          | Type             | Required | Default          | Description                                   |
|----------------|------------------|----------|------------------|-----------------------------------------------|
| `id`           | int or None      | No       | None             | Primary key (assigned by DB)                  |
| `name`         | string           | Yes      | —                | Human-readable policy name                    |
| `body`         | dict             | Yes      | —                | JSON rule body (Guardrail configuration)      |
| `remote_id`    | string or None   | No       | None             | Vendor-side policy identifier                 |
| `provider_id`  | int or None      | No       | None             | FK → Provider (which provider it belongs to)  |
| `is_active`    | boolean          | No       | True             | Activity flag (Soft Delete)                   |
| `created_at`   | datetime         | No       | current UTC time (via factory) | Record creation timestamp     |
| `updated_at`   | datetime         | No       | current UTC time (via factory) | Last update timestamp         |

### Validation

- `name`: minimum 1 character, maximum 200 characters.
- `body`: non-empty dict (minimum 1 key).
- `remote_id`: if provided — non-empty string.

---

## 3. Error Handling

The model raises a standard pydantic.ValidationError on invalid data.
No custom error handling is provided at the entity level — this is the responsibility of upstream layers (services, api).

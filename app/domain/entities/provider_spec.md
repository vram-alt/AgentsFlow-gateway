# Specification: Domain Entity Provider (provider.py)

> **Implementation file:** `provider.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Describing the "Provider" business entity — access settings for an external LLM provider

---

## 1. General Rules

- The model inherits from BaseModel (Pydantic).
- Uses Pydantic V2 (configuration via ConfigDict).
- Date fields have type datetime. The default value is set via a factory mechanism (default_factory) that retrieves the current UTC time **on each instance creation**, not once at module import. Use the timezone-aware variant for obtaining the current time (with explicit UTC timezone), as the timezone-naive variant is deprecated starting with Python 3.12.
- Boolean activity flags default to True.
- The model **does not contain** database logic — it is a pure domain object.

---

## 2. Entity: Provider

### Purpose

Stores credentials for connecting to an external LLM provider (currently — Portkey).

### Fields

| Field          | Type             | Required | Default          | Description                                   |
|----------------|------------------|----------|------------------|-----------------------------------------------|
| `id`           | int or None      | No       | None             | Primary key (assigned by DB)                  |
| `name`         | string           | Yes      | —                | Unique provider name (e.g., "Portkey")        |
| `api_key`      | string           | Yes      | —                | API key for authentication                    |
| `base_url`     | string           | Yes      | —                | Base URL of the provider API                  |
| `is_active`    | boolean          | No       | True             | Activity flag (Soft Delete)                   |
| `created_at`   | datetime         | No       | current UTC time (via factory) | Record creation timestamp     |
| `updated_at`   | datetime         | No       | current UTC time (via factory) | Last update timestamp         |

### Validation

- `name`: minimum 1 character, maximum 100 characters, strip_whitespace=True.
- `api_key`: minimum 1 character (non-empty string).
- `base_url`: must start with "http://" or "https://".

---

## 3. Error Handling

The model raises a standard pydantic.ValidationError on invalid data.
No custom error handling is provided at the entity level — this is the responsibility of upstream layers (services, api).

# Specification: Application Configuration (config.py)

> **Implementation file:** `config.py`  
> **Layer:** Root  
> **Responsibility:** Centralized reading of environment variables via Pydantic Settings

---

## 1. General Rules

- Configuration is implemented via the Pydantic Settings mechanism (inheriting from BaseSettings).
- All secrets are read from the `.env` file (the file path is specified in the model configuration).
- The `Settings` class is a singleton (via memoization, one instance per process).
- No secrets are **hardcoded** in the source code.

---

## 2. Class: Settings

### Fields

| Field                   | Type   | Required | Default                                   | Env Variable            |
|-------------------------|--------|----------|-------------------------------------------|-------------------------|
| `database_url`          | `str`  | No       | `"sqlite+aiosqlite:///./gateway.db"`      | `DATABASE_URL`          |
| `admin_username`        | `str`  | Yes      | —                                         | `ADMIN_USERNAME`        |
| `admin_password`        | `str`  | Yes      | —                                         | `ADMIN_PASSWORD`        |
| `webhook_secret`        | `str`  | Yes      | —                                         | `WEBHOOK_SECRET`        |
| `encryption_key`        | `str`  | Yes      | —                                         | `ENCRYPTION_KEY`        |
| `external_http_timeout` | `int`  | No       | `30`                                      | `EXTERNAL_HTTP_TIMEOUT` |

### Validation

- `database_url`: non-empty string.
- `admin_username`: required field with no default value. The validator must reject trivially predictable values (such as "admin", "root", "administrator") — raise a validation error upon detection.
- `admin_password`: minimum 12 characters. The validator must verify the presence of at least one digit and at least one special character. On failure — raise a validation error describing the password complexity requirements.
- `webhook_secret`: minimum 16 characters.
- `encryption_key`: required field. The validator must verify that the value is a valid Fernet key (a string of exactly 44 characters in base64 encoding). On failure — raise a validation error describing the key format. The key is used for symmetric encryption of provider API keys in the database.
- `external_http_timeout`: positive integer, range [5, 120].

### Requirements for the `.env.example` File

- The `.env.example` file must contain **valid examples** that pass all validators above. Trivial values are prohibited (e.g., "admin" for the username or a password without digits and special characters), as the application will not start with invalid values and will mislead developers on first launch.

---

## 3. Function: get_settings

### Purpose

Returns a cached (singleton) instance of `Settings`. Caching is implemented via memoization (one instance per process). Used as a dependency (Depends) in FastAPI routes.

### Input Parameters

None.

### Return Value

An instance of `Settings`.

---

## 4. Error Handling

| Scenario                        | Action                                            |
|---------------------------------|---------------------------------------------------|
| `.env` file not found           | Use default values + warning                      |
| Required field not set          | `ValidationError` at startup → application fails to start |
| Invalid value                   | `ValidationError` at startup → application fails to start |

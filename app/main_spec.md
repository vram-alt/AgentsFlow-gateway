# Specification: Application Entry Point (main.py)

> **Implementation file:** `main.py`  
> **Layer:** Root (composition of all layers)  
> **Responsibility:** Creating and configuring the FastAPI instance, attaching routers, lifespan events

---

## 1. General Rules

- `main.py` is the only file that "knows" about all layers and assembles them together.
- Business logic is **prohibited** in this file.
- Configuration is read from `config.py` (Pydantic Settings).

---

## 2. Creating the FastAPI Application

### Instance Parameters

| Parameter     | Value                                                 |
|---------------|-------------------------------------------------------|
| `title`       | `"AI Gateway Adapter"`                                |
| `description` | `"Phase 3 POC — Intelligent proxy for LLM providers"` |
| `version`     | `"0.1.0"`                                             |
| `lifespan`    | Reference to the async lifecycle manager              |

---

## 3. Lifespan (Lifecycle Events)

### 3.1. Startup

**Step-by-step logic:**

1. Load configuration from `.env` via `config.get_settings()`.
2. Initialize the database: call `init_db()` (table creation).
3. Log: `"AI Gateway started successfully"`.

### 3.2. Shutdown

**Step-by-step logic:**

1. Close the database connection pool: `engine.dispose()`.
2. Log: `"AI Gateway shut down"`.

### 3.3. Initialization Order (Startup Order)

Routers `stats_router` and `tester_router` depend on DI factories `get_log_service`, `get_tester_service`, `get_http_client`. All these factories require `PortkeyAdapter` to be initialized during lifespan startup. FastAPI guarantees completion of lifespan startup before accepting requests; however:
- A smoke test must be added to verify that after application startup, calling `get_http_client()` does not return an error.
- If lifespan startup fails (adapter not initialized), the application MUST NOT accept requests.

---

## 4. Router Registration

The application registers the following routers:

**API routes (with `/api/` prefix):**

| Router             | Prefix             | Tags          | Registration Condition          |
|--------------------|--------------------|--------------|---------------------------------|
| chat_router        | `/api/chat`        | Chat          | Unconditional                   |
| policies_router    | `/api/policies`    | Policies      | Unconditional                   |
| webhook_router     | `/api/webhook`     | Webhook       | Unconditional                   |
| logs_router        | `/api/logs`        | Logs          | Unconditional                   |
| providers_router   | `/api/providers`   | Providers     | Unconditional                   |
| stats_router       | (defined in router) | Stats        | Unconditional                   |
| tester_router      | (defined in router) | Tester       | Only if `settings.enable_tester_console` = True |

**UI routes (no prefix):**

| Router             | Prefix | Tags |
|--------------------|--------|------|
| ui_pages_router    | `/`    | UI   |

**Registration order:** chat, policies, providers, webhook, logs, stats, tester (conditional).

---

## 5. Global Exception Handler

### 5.1. Handling `GatewayError`

If a service returns a `GatewayError` and it is not handled in the route, the global handler intercepts it and:

1. Writes the full error text and traceback to the server log.
2. Returns a JSON response to the client with the HTTP status from `GatewayError.status_code`:
   - Field `error_code` — value from `GatewayError.error_code`.
   - Field `message` — value from `GatewayError.message`.
   - Field `trace_id` — value from `GatewayError.trace_id`.

### 5.2. Handling All Other Exceptions (Information Leakage Prevention)

The global handler intercepts **all** unhandled exceptions that are not `GatewayError` and:

1. Generates a unique UUID (trace_id) for correlation with the server log.
2. Writes the **full** exception text, traceback, and generated trace_id to the server log (ERROR level).
3. Returns a JSON response to the client with HTTP 500, containing **only** a generic message:
   - Field `error_code` — value `"UNKNOWN"`.
   - Field `message` — fixed string `"Internal server error"` (without any exception details, file paths, DB table names, or internal URLs).
   - Field `trace_id` — generated UUID for correlation.
4. It is **strictly prohibited** to transmit the exception text, stack trace, or any internal system information to the client.

### 5.3. Handling `ValidationError` (Pydantic)

FastAPI handles this automatically → HTTP 422.

---

## 6. Security (Attack Surface)

Router registration adds endpoints, including a proxy to external APIs (`/api/tester/proxy`) and data export (`/api/logs/export`). Requirements:
- All endpoints MUST have a security scheme in the OpenAPI documentation (HTTP Basic Auth).
- All endpoints MUST have an explicit `deprecated=False` annotation in OpenAPI.
- The `tester_router` MUST be toggleable via the feature flag `settings.enable_tester_console` (default False in production).

---

## 7. Error Handling

| Scenario                        | Action                                            |
|---------------------------------|---------------------------------------------------|
| Failed to connect to database   | Log CRITICAL, terminate process                   |
| `.env` file not found           | Use default values + warning                      |
| Error creating tables           | Log CRITICAL, terminate process                   |

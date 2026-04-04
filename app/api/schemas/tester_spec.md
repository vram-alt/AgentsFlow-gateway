# Specification: app/api/schemas/tester.py

## Purpose

Pydantic V2 schemas for the "Testing Console" module endpoints. Implements the file `app/api/schemas/tester.py`.

---

## §1. Schema: TesterProxyRequest

Request body for POST /api/tester/proxy.

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `provider_name` | str | Yes | — | Minimum length: 1 character. |
| `method` | str | No | "POST" | Allowed values (case-insensitive): "GET", "POST", "PUT", "DELETE". Normalize to uppercase. |
| `path` | str | No | "/chat/completions" | See §1.1 (extended validation). |
| `body` | dict or None | No | None | See §1.2 (size limit). |
| `headers` | dict or None | No | None | See §1.3 (count and length limits). |

### §1.1 Field `path` Validation

The `path` field validator MUST perform the following checks:
1. URL-decode the `path` value before checking (to prevent bypass via percent-encoding, e.g., `%2e%2e` instead of `..`).
2. Verify that the decoded `path` does not contain the substring `://` (absolute URL prohibition).
3. Verify that the decoded `path` does not contain the substring `..` (path traversal prohibition).
4. On any violation — reject with a validation error.

### §1.2 Field `body` Validation (Size Limit)

The `body` field of type `dict | None` MUST undergo additional validation via model_validator:
1. If `body` is not None — serialize it to a JSON string and verify that the string length does not exceed 1,048,576 bytes (1 MB).
2. On exceeding — reject with validation error "Request body too large (max 1MB)".
3. This prevents sending JSON bodies of hundreds of megabytes and protects against deeply nested structures causing `RecursionError`.

### §1.3 Field `headers` Validation (Count and Length Limits)

The `headers` field of type `dict | None` MUST undergo additional validation:
1. Maximum number of headers — 20. On exceeding — reject with error "Too many headers (max 20)".
2. Maximum header key length — 128 characters. On exceeding — reject with error "Header name too long (max 128 chars)".
3. Maximum header value length — 4096 characters. On exceeding — reject with error "Header value too long (max 4096 chars)".
4. This prevents attacks via sending thousands of headers with arbitrarily long values.

---

## §2. Schema: TesterProxyResponse

Response for POST /api/tester/proxy (success).

| Field | Type | Description |
|---|---|---|
| `status_code` | int | HTTP status code from the provider response. |
| `headers` | dict with string keys and values | Filtered response headers. |
| `body` | Any (dict, list, or str) | Response body from the provider (JSON or raw text). |
| `latency_ms` | float | Request execution time in milliseconds. |

---

## §3. Schema: TesterErrorResponse

Error response for tester endpoints.

| Field | Type | Description |
|---|---|---|
| `trace_id` | str | UUID v4 for tracing. |
| `error_code` | str | Error code (PROVIDER_NOT_FOUND, PROXY_TIMEOUT, PROXY_CONNECTION_ERROR, VALIDATION_ERROR, INTERNAL_ERROR, RESPONSE_TOO_LARGE). |
| `message` | str | Human-readable error description. |

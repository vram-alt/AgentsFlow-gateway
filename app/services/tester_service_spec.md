# Specification: app/services/tester_service.py

## Purpose

The `TesterService` is the orchestrator for the "Testing Console" module. It accepts proxy request parameters from the router, fetches provider credentials from the DB, executes an HTTP request to the external LLM API, and returns the raw result. Implements the file `app/services/tester_service.py`.

---

## §1. Class: TesterService

### §1.1 Constructor

Accepts two arguments:
- `provider_repo` — a `ProviderRepository` instance for accessing the providers table.
- `http_client` — an `httpx.AsyncClient` instance for executing HTTP requests. Reused (not created anew per request).

### §1.2 Method: proxy_request

**Signature**: async method accepting five arguments:
- `provider_name` — string, provider name.
- `method` — string, HTTP method (GET, POST, PUT, DELETE).
- `path` — string, relative endpoint path on the provider side.
- `body` — dict or None, request body.
- `headers` — dict or None, additional user-supplied headers.

**Returns**: dict with the result or a GatewayError object.

**Algorithm**:

1. **Path validation**: URL-decode `path` before checking (to prevent bypass via percent-encoding). Verify that the decoded `path` does not contain `://` and does not start with `..`. If it does — return GatewayError with error_code "VALIDATION_ERROR" and status 422.

2. **Fetch provider**: call `provider_repo.get_active_by_name(provider_name)`.
   - If result is None — return GatewayError with error_code "PROVIDER_NOT_FOUND" and status 404.
   - Extract `api_key` and `base_url` from the provider record.

3. **Build URL**: concatenate `base_url` (with trailing `/` removed) and `path` (with leading `/` removed), separated by a single `/`.

4. **Final URL validation (SSRF protection)**: after building the final URL, parse it and verify:
   - Scheme MUST be "https". "http" is allowed only if the application is running in dev mode (determined via settings).
   - Hostname MUST NOT be a private IP address. Prohibited addresses: 127.0.0.1, ::1, ranges 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, and 169.254.169.254 (AWS/cloud metadata endpoint).
   - The final URL hostname MUST match the hostname from the provider's `base_url` (protection against substitution via path manipulation like `@evil.com/`).
   - On any violation — return GatewayError with error_code "VALIDATION_ERROR" and status 422.

5. **Build headers**:
   - Start with a dict of required headers: `x-portkey-api-key` with value `api_key`, `Content-Type` with value `application/json`.
   - If the user provided additional headers (`headers` is not None) — add them, but DO NOT overwrite the `x-portkey-api-key` key (case-insensitive comparison).

6. **Time measurement**: record the request start time (monotonic clock).

7. **Timeout configuration**: use granular timeouts instead of a single value. Connect timeout = 5 seconds (for DNS resolution and connection establishment). Read timeout = value from application settings (`settings.external_http_timeout`). Write timeout = 10 seconds. Pool timeout = 5 seconds.

8. **Execute HTTP request**: send the request via `http_client.request(method, url, headers, json=body)` with granular timeouts from step 7.
   - Exception handling:
     - Timeout — return GatewayError with error_code "PROXY_TIMEOUT", status 504.
     - Connection error — return GatewayError with error_code "PROXY_CONNECTION_ERROR", status 502.
     - Any other exception — return GatewayError with error_code "INTERNAL_ERROR", status 500.

9. **Time measurement**: compute latency_ms as the difference between current time and start time, multiplied by 1000, rounded to 2 decimal places.

10. **Response size limit**: before reading the response body, check its size. Read the response body with a limit: maximum allowed size — 10 MB (10,485,760 bytes). If the body size exceeds the limit — return GatewayError with error_code "RESPONSE_TOO_LARGE" and status 502.

11. **Response parsing**:
   - Attempt to parse the response body as JSON.
   - If parsing fails — use the text representation of the response body.

12. **Build result**: return a dict with keys:
   - `status_code` — HTTP status code from the provider response (integer).
   - `headers` — dict with filtered response headers. Include only: `content-type`, `x-request-id`, `x-portkey-trace-id`, `retry-after`. All other headers are discarded for security.
   - `body` — parsed JSON or string with raw text.
   - `latency_ms` — float.

---

## §2. Error Handling

- All errors are returned as GatewayError objects (not raised as exceptions).
- Each GatewayError contains a unique `trace_id` (UUID v4), generated at the beginning of the method.
- The provider API key is NEVER included in error messages and is NEVER logged.

---

## §3. Logging

- On proxy request start — log at INFO level: provider_name, method, path (without API key). Request body (`body`) and headers (`headers`) are NOT logged at INFO level (may contain PII).
- On error — log at ERROR level: trace_id, error_code, message (without API key, without body).
- On successful completion — log at INFO level: trace_id, status_code, latency_ms.
- At DEBUG level, logging of method and path is permitted, but NEVER body, headers, or api_key.

---

## §4. Security

- The provider API key is used only for building the request header and is NEVER returned to the client.
- The `x-portkey-api-key` header is protected from overwrite by user-supplied headers.
- The `path` is URL-decoded before validation, then checked for the absence of path traversal (`..`) and absolute URLs (`://`).
- The final URL undergoes SSRF validation: scheme check, private IP prohibition, hostname match with the provider's base_url (see §1.2 step 4).
- Provider response size is limited to 10 MB to prevent OOM (see §1.2 step 10).
- Granular timeouts prevent hanging on DNS resolution (see §1.2 step 7).
- Logging of request body and headers is explicitly prohibited at INFO level and above (see §3).

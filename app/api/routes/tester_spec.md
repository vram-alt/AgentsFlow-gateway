# Specification: app/api/routes/tester.py

## Purpose

Router for the "Testing Console" module — provides endpoints for interactive LLM provider testing from the UI. Allows retrieving a JSON schema for the test form and sending arbitrary requests to a provider via proxy. Implements the file `app/api/routes/tester.py`.

---

## §1. General Information

- **Prefix**: `/api/tester`
- **OpenAPI Tags**: `["Tester"]`
- **Authentication**: all endpoints are protected by the `get_current_user` dependency (HTTP Basic Auth).
- **Dependencies**: `TesterService` (via DI factory `get_tester_service`).

---

## §2. Endpoint: GET /api/tester/schema

### §2.1 Purpose

Returns a hardcoded JSON schema describing the test console form fields. The frontend uses this schema for dynamic UI form generation.

### §2.2 Request Parameters

No parameters (besides authentication).

### §2.3 Processing Algorithm

1. Return a static dict describing the test form structure.
2. No DB or external service calls are required.

### §2.4 Response Format (HTTP 200)

Dict with the following structure:

- `fields` — list of dicts, each describing one form field:
  - `name` — string, field name (identifier for the frontend).
  - `type` — string, field type: "text", "textarea", "select", "number".
  - `label` — string, human-readable field label.
  - `required` — boolean, whether the field is mandatory.
  - `default` — default value (string, number, or null).
  - `options` — list of strings (only for type="select"), allowed values. For other types — null.

Required form fields:
1. `provider_name` — select, required, options: "portkey". Default: "portkey".
2. `model` — text, required, no default value.
3. `prompt` — textarea, required, no default value.
4. `temperature` — number, optional, default: 0.7.
5. `max_tokens` — number, optional, default: 1024.

### §2.5 Error Handling

Errors are unlikely (static data). On any unexpected exception — HTTP 500 with `detail` key.

---

## §3. Endpoint: POST /api/tester/proxy

### §3.1 Purpose

Accepts an arbitrary JSON request from the UI, attaches the API key and base_url from the DB for the specified provider, sends the request to the external LLM API, and returns the raw response. This is a "transparent proxy" for testing.

### §3.2 Request Body (JSON)

Pydantic schema `TesterProxyRequest` (detailed validation described in `tester_spec.md` for schemas):

| Field | Type | Required | Description |
|---|---|---|---|
| `provider_name` | str | Yes | Provider name from the providers table (e.g., "portkey"). |
| `method` | str | No (default "POST") | HTTP method for the provider request. Allowed values: "GET", "POST", "PUT", "DELETE". |
| `path` | str | No (default "/chat/completions") | Endpoint path on the provider side (appended to base_url). URL-decoded and validated for path traversal and absolute URLs. |
| `body` | dict or null | No (default null) | Arbitrary JSON request body. Maximum serialized JSON size — 1 MB. Passed as-is to the provider. |
| `headers` | dict or null | No (default null) | Additional HTTP headers. Maximum 20 headers, key length <= 128, value length <= 4096. Filtered via allowlist (see §5.3). |

### §3.3 Processing Algorithm

1. Validate the request body via Pydantic schema (including body size limits, header count, URL-decoding of path).
2. Call `tester_service.proxy_request(provider_name, method, path, body, headers)`.
3. Inside the service:
   a. Fetch the provider from DB via `ProviderRepository.get_active_by_name(provider_name)`.
   b. If provider not found — return error (see §3.5).
   c. Build the full URL: `base_url.rstrip("/") + "/" + path.lstrip("/")`.
   d. **SSRF validation of the final URL**: parse the final URL and verify that the resulting URL hostname matches the hostname from the provider's `base_url`. Reject requests to private IP addresses: 127.0.0.1, ::1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254 (AWS/cloud metadata). Scheme must be "https" (or "http" only in dev mode). On violation — return VALIDATION_ERROR (422).
   e. **Header filtering**: build headers starting with required ones (API key via `x-portkey-api-key`, `Content-Type`). User headers are filtered via allowlist (see §5.3). The API key header is NOT overwritten.
   f. Execute the HTTP request via httpx.AsyncClient with granular timeouts (connect=5s, read=from settings, write=10s, pool=5s).
   g. Limit response size: maximum 10 MB. On exceeding — return RESPONSE_TOO_LARGE (502).
   h. Return the result.
4. The router builds the response from the service result.

### §3.4 Response Format (HTTP 200)

Dict with keys:
- `status_code` — integer, HTTP status code from the provider response.
- `headers` — dict of strings, response headers from the provider (only essential: content-type, x-request-id, x-portkey-trace-id, retry-after).
- `body` — arbitrary JSON (dict or list), response body from the provider. If the response is not valid JSON — a string with raw text.
- `latency_ms` — float, request execution time in milliseconds.

### §3.5 Error Handling

| Scenario | HTTP Status | error_code | Description |
|---|---|---|---|
| Provider not found in DB | 404 | PROVIDER_NOT_FOUND | Provider with the specified name does not exist or is deactivated. |
| Request timeout to provider | 504 | PROXY_TIMEOUT | External provider did not respond within the timeout. |
| Connection error with provider | 502 | PROXY_CONNECTION_ERROR | Failed to establish connection with the provider. |
| Provider response too large | 502 | RESPONSE_TOO_LARGE | Response size exceeds 10 MB. |
| Invalid request body | 422 | VALIDATION_ERROR | Standard FastAPI/Pydantic validation error. |
| SSRF validation failed | 422 | VALIDATION_ERROR | Final URL points to a private IP or hostname does not match base_url. |
| Any other error | 500 | INTERNAL_ERROR | Unexpected error. |

All error responses contain `trace_id` (UUID v4), `error_code`, and `message`.

---

## §4. Pydantic Schemas

Define in file `app/api/schemas/tester.py`:

1. **TesterProxyRequest** — request body schema for POST /api/tester/proxy (fields described in §3.2, validation described in `tester_spec.md` for schemas).
2. **TesterProxyResponse** — response schema (fields described in §3.4).
3. **TesterErrorResponse** — error schema with fields: `trace_id`, `error_code`, `message`.

---

## §5. Security

### §5.1 Authentication and API Keys

- All endpoints require HTTP Basic Auth via the `get_current_user` dependency.
- The provider API key is NEVER returned to the client in the response. It is used only for building the request to the external API.
- The API key header (`x-portkey-api-key`) cannot be overwritten by user-supplied headers from the `headers` request field.

### §5.2 Path Validation and SSRF Protection

- The user-supplied `path` is URL-decoded before validation, then checked for the absence of path traversal (`..`) and absolute URLs (`://`). On violation — reject with HTTP 422.
- The final URL (after base_url + path concatenation) undergoes SSRF validation: scheme check, private IP prohibition, hostname match with the provider's base_url (see §3.3 step d).

### §5.3 Header Filtering (Header Injection Protection)

User-supplied headers from the `headers` request field are filtered via an **allowlist** (not a blocklist). Allowed user headers:
- `Accept`
- `Accept-Language`
- `Accept-Encoding`
- Headers with prefix `X-Custom-`

All other headers are rejected. In particular, hop-by-hop headers are PROHIBITED: `Connection`, `Transfer-Encoding`, `Host`, `Proxy-Authorization`, `Upgrade`, `Keep-Alive`, `TE`, `Trailer`. This prevents HTTP request smuggling.

### §5.4 Size Limits

- Maximum request body size (`body`) — 1 MB (validation at Pydantic schema level, see `tester_spec.md` for schemas §1.2).
- Maximum provider response size — 10 MB (validation at service level, see `tester_service_spec.md` §1.2 step 10).

### §5.5 Logging (PII Protection)

- Logging of request `body` and `headers` is PROHIBITED at INFO level and above. These fields may contain PII (user personal data, prompts).
- At INFO level, ONLY the following are logged: `provider_name`, `method`, `path`, `status_code`.
- At DEBUG level, logging of method and path is permitted, but NEVER body, headers, or api_key.

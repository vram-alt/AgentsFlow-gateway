# Specification: Portkey Adapter

> **Implementation file:** `portkey_adapter.py`  
> **Layer:** Infrastructure → Adapters  
> **Responsibility:** Implementation of the `GatewayProvider` contract for the Portkey provider  
> **Dependencies:** `httpx`, domain DTOs, `GatewayProvider` contract

---

## 1. General Rules

- The `PortkeyAdapter` class implements the abstract `GatewayProvider` interface.
- All HTTP calls are executed via `httpx.AsyncClient`.
- Mandatory timeout on all requests: value from `EXTERNAL_HTTP_TIMEOUT` (default 30 sec).
- Format transformation (Portkey ↔ DTO) occurs **exclusively** within this module.
- Methods **never raise exceptions** to the caller — all errors are wrapped in `GatewayError`.

### 1.1. Retry Policy

All HTTP calls to the external API must use a retry mechanism with exponential backoff:

- **Maximum attempts:** 3 (initial request + 2 retries).
- **Delays between attempts:** 1 second, 2 seconds, 4 seconds (exponential growth).
- **Retry conditions for GET requests:** transient errors — HTTP 502, 503, connection errors, timeouts.
- **Retry conditions for POST/PUT/DELETE requests:** retry **only** on explicit HTTP 502 and 503 (not on timeouts and connection errors, as the request may have been partially processed).
- **On exhausted attempts:** return `GatewayError` with information about the last error.

### 1.2. HTTP Client Lifecycle Management

The reusable HTTP client must have an explicitly defined lifecycle:

- The adapter must provide an async method for graceful client closure.
- This method must be called during the application's lifespan shutdown event for proper release of TCP connections and file descriptors.
- When the close method cannot be called (e.g., in tests) — creating a new HTTP client per request via a context manager is acceptable.

---

## 2. Property: provider_name

- Returns the string `"portkey"`.

---

## 3. Method: send_prompt

### Interface Description

- **Async method** accepting three parameters: `prompt` (type UnifiedPrompt), `api_key` (string), `base_url` (string).
- **Returns:** UnifiedResponse on success or GatewayError on error.

### Step-by-Step Logic

1. **Build headers:**
   - Portkey API key header (header name: `x-portkey-api-key`).
   - Content type header: `application/json`.
   - Request correlation identifier header (header name: `x-portkey-trace-id`) — for linking with webhooks.
   - If the Guardrail identifier list in the prompt is not empty → add header `x-portkey-guardrails` with the ID list in JSON array format.

2. **Build request body:**
   - Request body — a JSON object containing: model identifier from the prompt, message array (each with role and content fields), temperature (if provided), maximum token count (if provided), metadata (including trace_id and arbitrary metadata from the prompt).

3. **Send POST request:**
   - URL: `{base_url}/chat/completions`
   - Timeout: `EXTERNAL_HTTP_TIMEOUT` seconds.

4. **Handle successful response (HTTP 200):**
   - Extract `choices[0].message.content` → `content`.
   - Extract `model` → `model`.
   - Extract `usage` → `UsageInfo` (if present).
   - Check for Guardrail block flag in the response.
   - Assemble `UnifiedResponse`.

5. **Error handling:**

   | HTTP Status | GatewayError Code   | Description                       |
   |-------------|---------------------|-----------------------------------|
   | 401, 403    | `AUTH_FAILED`       | Invalid API key                   |
   | 429         | `RATE_LIMITED`      | Request rate limit exceeded       |
   | 400         | `VALIDATION_ERROR`  | Invalid request                   |
   | 500+        | `PROVIDER_ERROR`    | Internal Portkey error            |
   | Timeout     | `TIMEOUT`           | Response timeout exceeded         |
   | Other       | `UNKNOWN`           | Unknown error                     |

---

## 4. Method: create_guardrail

### Interface Description

- **Async method** accepting three parameters: `config` (dict with Guardrail configuration), `api_key` (string), `base_url` (string).
- **Returns:** dict with key `remote_id` on success or GatewayError on error.

### Step-by-Step Logic

1. **Build headers:**
   - `x-portkey-api-key: {api_key}`
   - `Content-Type: application/json`

2. **Send POST request:**
   - URL: `{base_url}/guardrails`
   - Body: `config` (Guardrail JSON configuration as-is).

3. **Handle successful response:**
   - Extract `id` from response → this is the `remote_id`.
   - Return `{"remote_id": id, "raw_response": response_body}`.

4. **Error handling:** same as `send_prompt`.

---

## 5. Method: update_guardrail

### Interface Description

- **Async method** accepting four parameters: `remote_id` (string — vendor-side policy identifier), `config` (dict with new configuration), `api_key` (string), `base_url` (string).
- **Returns:** dict with updated metadata on success or GatewayError on error.

### Step-by-Step Logic

1. **Send PUT request:**
   - URL: `{base_url}/guardrails/{remote_id}`
   - Body: `config`.

2. **Response handling:** same as `create_guardrail`.

---

## 6. Method: delete_guardrail

### Interface Description

- **Async method** accepting three parameters: `remote_id` (string), `api_key` (string), `base_url` (string).
- **Returns:** boolean True on success or GatewayError on error.

### Step-by-Step Logic

1. **Send DELETE request:**
   - URL: `{base_url}/guardrails/{remote_id}`

2. **Response handling:**
   - HTTP 200/204 → return `True`.
   - Otherwise → `GatewayError`.

---

## 7. Method: list_guardrails

### Interface Description

- **Async method** accepting two parameters: `api_key` (string), `base_url` (string).
- **Returns:** list of dicts on success or GatewayError on error.

### Step-by-Step Logic

1. **Send GET request:**
   - URL: `{base_url}/guardrails`

2. **Response handling:**
   - Extract the policy array from the response body.
   - For each policy, return a dict with keys: `remote_id`, `name`, `config`.

---

## 8. Internal Helper Methods

### 8.1. `_build_headers(api_key: str) -> dict`

Builds the standard set of HTTP headers for the Portkey API.

### 8.2. `_handle_error(exc: Exception, trace_id: str | None) -> GatewayError`

Converts any exception (`httpx.TimeoutException`, `httpx.HTTPStatusError`, etc.)
into the corresponding `GatewayError` with the correct error code.

### 8.3. `_get_http_client() -> httpx.AsyncClient`

Creates or returns a reusable `httpx.AsyncClient` with a configured timeout. The client is stored as an adapter instance attribute and reused between calls.

### 8.4. `async close() -> None`

Gracefully closes the reusable HTTP client, releasing TCP connections and file descriptors. Must be called during application shutdown (lifespan shutdown event). After calling, the adapter should not be used for HTTP requests without reinitializing the client.

### 8.5. `_execute_with_retry(method, url, ...) -> httpx.Response`

Internal method implementing the retry policy (see section 1.1). Accepts the HTTP method, URL, and request parameters. Executes the request with retry logic according to the rules for the given HTTP method. On exhausted attempts — raises the last received exception for handling in the calling method.

---

## 9. Error Handling (Summary Table)

| httpx Exception                 | GatewayError Code   | HTTP Status |
|---------------------------------|---------------------|-------------|
| `httpx.TimeoutException`        | `TIMEOUT`           | 504         |
| `httpx.ConnectError`            | `PROVIDER_ERROR`    | 502         |
| `httpx.HTTPStatusError` (4xx)   | depends on status   | original    |
| `httpx.HTTPStatusError` (5xx)   | `PROVIDER_ERROR`    | 502         |
| `json.JSONDecodeError`          | `PROVIDER_ERROR`    | 502         |
| Any other `Exception`           | `UNKNOWN`           | 500         |

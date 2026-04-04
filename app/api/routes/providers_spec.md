# Specification: Providers Router (providers.py)

> **Implementation file:** `providers.py`  
> **Layer:** API / Delivery  
> **Responsibility:** HTTP handlers for CRUD operations on LLM providers and health checks

---

## 1. General Rules

- Routes are thin wrappers: accept an HTTP request, call the service, return an HTTP response.
- Business logic is **prohibited** in routes — only routing and transformation.
- All dependencies are obtained via FastAPI Depends.
- Pydantic schemas for request/response are defined in this file.

---

## 2. Router

**Prefix:** `/api/providers`  
**Tags:** "Providers"  
**Protection:** HTTP Basic Auth.

**Important: registration order.** The `/api/providers/health` endpoint MUST be registered BEFORE the `/api/providers/{provider_id}` endpoint, otherwise FastAPI interprets "health" as a value for the `provider_id` parameter. Place the route decorator above the existing parameterized routes in the file.

---

## 3. Endpoint: GET /api/providers/

### Purpose

List all providers.

---

## 4. Endpoint: POST /api/providers/

### Purpose

Create a new provider.

### Request Body (ProviderCreateRequest schema)

| Field      | Type   | Required | Description                 |
|------------|--------|----------|-----------------------------|
| `name`     | string | Yes      | Provider name               |
| `api_key`  | string | Yes      | API key for authentication  |
| `base_url` | string | Yes      | Base URL of the provider API|

---

## 5. Endpoint: GET /api/providers/health

### Purpose

Returns the availability status of all active LLM providers. Used by the dashboard to display a provider status "traffic light".

### Request Parameters

No parameters (besides authentication).

### Dependencies

- `ProviderService` — via existing DI factory `get_provider_service`.
- `httpx.AsyncClient` — via DI factory `get_http_client`.

### Processing Algorithm

1. Get `provider_service` and `http_client` via DI.
2. **Caching**: before calling the service, check the in-memory health-check result cache. The cache is stored as a module variable (dict with `result` and `timestamp` keys). If the cache exists and its age is less than 30 seconds (TTL=30s) — return the cached result without executing network requests. This prevents cascading failures during frequent dashboard polling: if providers respond slowly, accumulated pending requests won't exhaust the httpx connection pool.
3. If cache is absent or stale — call `provider_service.check_health(http_client)`.
4. Save the result to cache with the current timestamp.
5. Return the result as a JSON array with status 200.

### Response Format (HTTP 200)

JSON array of dicts, each containing:
- `id` — integer.
- `name` — string.
- `base_url_masked` — string (masked URL: only scheme and hostname).
- `is_active` — boolean.
- `status` — string: "healthy", "timeout", "unreachable", "error".
- `response_time_ms` — float or null.

### Testing

To protect against regression during refactoring — an integration test MUST be added that verifies `GET /api/providers/health` returns HTTP 200 (not 422, which would indicate "health" being parsed as an integer for the `provider_id` parameter).

---

## 6. Endpoint: PUT /api/providers/{provider_id}

### Purpose

Update a provider (change key, URL).

---

## 7. Endpoint: DELETE /api/providers/{provider_id}

### Purpose

Soft Delete a provider.

---

## 8. Security

- All endpoints require HTTP Basic Auth via the `get_current_user` dependency.
- Provider API keys are NOT returned in responses.
- The `base_url` field is masked in health checks (only scheme and hostname returned) to prevent internal infrastructure disclosure.
- Health checks are performed without provider-side authorization (HEAD request to base_url).
- Health-check results are cached for 30 seconds to protect against cascading failures during frequent polling.

---

## 9. Error Handling

| HTTP Status | When                                     |
|-------------|------------------------------------------|
| 200         | Successful operation                     |
| 201         | Successful resource creation             |
| 401         | Invalid token / unauthorized             |
| 404         | Resource not found                       |
| 422         | Invalid JSON (Pydantic)                  |
| 500         | Internal server error                    |

# Specification: Provider Management Service (ProviderService)

> **Implementation file:** `provider_service.py`  
> **Layer:** Services / Use Cases  
> **Responsibility:** Wrapper over ProviderRepository for CRUD operations and provider health checks

---

## 1. General Rules

- The service is a wrapper over `ProviderRepository` for managing LLM providers.
- All methods are asynchronous.
- Health-check business logic is encapsulated in this service.

---

## 2. Class: ProviderService

### Dependencies (via constructor)

| Parameter       | Type                 | Description                                     |
|-----------------|----------------------|-------------------------------------------------|
| `provider_repo` | `ProviderRepository` | Repository for CRUD operations on providers     |

---

## 3. Method: list_providers

### Purpose

Retrieve the list of all providers.

### Interface Description

- **Async method** accepting one parameter: `only_active` (boolean, default True).
- **Returns:** list of providers from the repository.

### Algorithm

1. Call `self.provider_repo.list_all(only_active=only_active)`.
2. Return the result.

---

## 4. Method: create_provider

### Purpose

Create a new provider.

### Interface Description

- **Async method** accepting three parameters: `name` (string), `api_key` (string), `base_url` (string).
- **Returns:** the created provider.

### Algorithm

1. Call `self.provider_repo.create(name=name, api_key=api_key, base_url=base_url)`.
2. Return the result.

---

## 5. Method: update_provider

### Purpose

Update a provider (change name, key, URL).

### Interface Description

- **Async method** accepting: `provider_id` (integer), `name` (string or None), `api_key` (string or None), `base_url` (string or None).
- **Returns:** updated provider or None.

### Algorithm

1. Collect a dict of fields to update from provided non-None parameters.
2. Call `self.provider_repo.update(provider_id, **fields)`.
3. Return the result.

---

## 6. Method: delete_provider

### Purpose

Soft delete a provider.

### Interface Description

- **Async method** accepting one parameter: `provider_id` (integer).
- **Returns:** operation result.

### Algorithm

1. Call `self.provider_repo.soft_delete(provider_id)`.
2. Return the result.

---

## 7. Method: check_health

### Purpose

Performs a health check on all active LLM providers. For each provider, sends a lightweight HTTP HEAD request to its `base_url` and returns the availability status.

### Interface Description

- **Async method** accepting one parameter: `http_client` (httpx.AsyncClient instance). Passed as a method argument (not via constructor) to avoid changing the constructor signature and breaking existing DI factories and tests.
- **Returns:** list of dicts (one per active provider).

### Algorithm

1. Call `self.provider_repo.list_all(only_active=True)` to get the list of active providers.
2. **Parallel execution**: for each provider, create an async check task. Run all tasks in parallel with exception handling. Set a global timeout for the entire task group — 15 seconds. If the global timeout expires — all incomplete providers receive status "timeout".
3. **SSRF validation**: before executing an HTTP request to the provider's `base_url` — parse the URL and verify that the hostname is NOT a private IP address. Prohibited addresses: 127.0.0.1, ::1, ranges 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, and 169.254.169.254 (AWS metadata endpoint). Validation is performed via DNS resolution of the hostname (for DNS rebinding attack protection). If `base_url` points to a private IP — skip the provider with status "error".
4. For each provider (within the parallel task):
   a. Attempt an HTTP HEAD request to `provider.base_url` with a 5-second timeout per individual request.
   b. If the request succeeds (any HTTP status received) — `status` = "healthy".
   c. If a timeout occurs — `status` = "timeout".
   d. If a connection error occurs — `status` = "unreachable".
   e. If any other error occurs — `status` = "error".
5. Build a dict for each provider:
   - `id` — integer, provider ID.
   - `name` — string, provider name.
   - `base_url_masked` — string, masked URL: only scheme and hostname (no path, query, fragment). For example, for "https://api.portkey.ai/v1/gateway" return "https://api.portkey.ai". The full `base_url` is NOT returned to the client to prevent internal infrastructure disclosure.
   - `is_active` — boolean (always true, since we filter by active).
   - `status` — string: "healthy", "timeout", "unreachable", or "error".
   - `response_time_ms` — float or null. Response time in milliseconds (only for status="healthy"). For other statuses — null.
6. Return the list of dicts.

### Logging

- On check start — INFO: "Starting health check for N providers".
- On individual provider error — WARNING: provider name, error type.
- On private IP detected in base_url — WARNING: provider name, "Private IP detected in base_url".
- On completion — INFO: "Health check completed: N healthy, M unhealthy".

---

## 8. Helper Function: _is_private_ip

### Purpose

Check whether a hostname is a private IP address (SSRF protection).

### Interface Description

- **Synchronous module-level function** accepting one parameter: `hostname` (string).
- **Returns:** boolean (True if IP is private).

### Algorithm

1. Strip square brackets from hostname (for IPv6).
2. Attempt to parse as a literal IP address. If successful — check if it is loopback, private, link-local, or equals 169.254.169.254. If so — return True.
3. If it is a hostname (not IP) — perform DNS resolution via socket.getaddrinfo and check ALL resolved IP addresses. If at least one is private — return True. This protects against DNS rebinding attacks.
4. On DNS resolution error — return False (provider will be checked and receive "unreachable" status).

---

## 9. Security

- SSRF validation of `base_url` is performed before every HTTP request (private IP prohibition with DNS rebinding protection).
- The `base_url` field is masked in the client response — only scheme and hostname are returned.
- The provider API key is NOT used and NOT disclosed during health checks.

---

## 10. Error Handling

| Scenario                                | Action                                                |
|-----------------------------------------|-------------------------------------------------------|
| Error fetching provider list            | Propagated upstream (handled by router)               |
| HTTP request timeout to provider        | status = "timeout", remaining checks continue         |
| Connection error with provider          | status = "unreachable", remaining checks continue     |
| Private IP in base_url                  | status = "error", WARNING log                         |
| Global 15-second timeout                | Incomplete providers receive status = "timeout"       |
| Any other HTTP request error            | status = "error", WARNING log                         |

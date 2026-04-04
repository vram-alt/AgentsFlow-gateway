# Specification: Dependencies (Dependency Injection)

> **Implementation file:** `di.py`  
> **Layer:** API / Delivery  
> **Responsibility:** Dependency factories for FastAPI Depends — assembling services, repositories, adapters

---

## 1. General Rules

- All dependencies are created via factory functions for FastAPI `Depends`.
- Each factory receives `AsyncSession` from `get_db_session()` and assembles the dependency graph.
- The provider adapter is created as a module-level singleton (stateless).
- Factories **do not contain** business logic.

---

## 2. Module: di.py

### 2.1. Factory: get_provider_repo

- **Dependencies:** AsyncSession (from get_db_session)
- **Returns:** ProviderRepository
- **Logic:** Creates a ProviderRepository instance, passing it the current DB session.

### 2.2. Factory: get_policy_repo

- **Dependencies:** AsyncSession (from get_db_session)
- **Returns:** PolicyRepository
- **Logic:** Creates a PolicyRepository instance, passing it the current DB session.

### 2.3. Factory: get_log_repo

- **Dependencies:** AsyncSession (from get_db_session)
- **Returns:** LogRepository
- **Logic:** Creates a LogRepository instance, passing it the current DB session.

### 2.4. Factory: get_adapter

- **Dependencies:** none (stateless)
- **Returns:** GatewayProvider (specifically — PortkeyAdapter)
- **Logic:** Returns a PortkeyAdapter instance. Since the adapter is stateless, reusing a single instance is acceptable.

### 2.5. Factory: get_log_service

- **Dependencies:** LogRepository (from get_log_repo)
- **Returns:** LogService
- **Logic:** Creates a LogService instance, passing it the LogRepository.

### 2.6. Factory: get_chat_service

- **Dependencies:** ProviderRepository (from get_provider_repo), LogService (from get_log_service), GatewayProvider (from get_adapter)
- **Returns:** ChatService
- **Logic:** Creates a ChatService instance, passing it all three dependencies.

### 2.7. Factory: get_policy_service

- **Dependencies:** PolicyRepository (from get_policy_repo), ProviderRepository (from get_provider_repo), LogService (from get_log_service), GatewayProvider (from get_adapter)
- **Returns:** PolicyService
- **Logic:** Creates a PolicyService instance, passing it all four dependencies.

### 2.8. Factory: get_webhook_service

- **Dependencies:** LogService (from get_log_service), LogRepository (from get_log_repo)
- **Returns:** WebhookService
- **Logic:** Creates a WebhookService instance, passing it LogService and LogRepository.

### 2.9. Factory: get_http_client

- **Dependencies:** GatewayProvider (from get_adapter)
- **Returns:** httpx.AsyncClient
- **Logic:**
  1. Get the adapter singleton via the existing `get_adapter()` factory.
  2. **Readiness check**: if the adapter is None (not initialized, race condition during startup) — return HTTP 503 with body "Service not ready". This prevents `AttributeError` when accessing an uninitialized adapter.
  3. Call the **public** method `get_http_client()` (without `_` prefix) on the adapter to obtain the reusable httpx client. The private method `_get_http_client()` MUST NOT be called from the DI factory — this violates encapsulation. A public method must be added to `PortkeyAdapter` (or to the `GatewayProvider` contract) that delegates to the private one.
  4. Return the client.
- **Rationale:** Reusing the HTTP client from the adapter avoids creating an additional connection pool for health checks, uses a single timeout from application settings, and properly closes the client on shutdown (already implemented in lifespan).

### 2.10. Factory: get_tester_http_client

- **Dependencies:** GatewayProvider (from get_adapter)
- **Returns:** httpx.AsyncClient (isolated instance)
- **Logic:**
  1. Get the adapter singleton via the existing `get_adapter()` factory.
  2. **Readiness check**: if the adapter is None — return HTTP 503 with body "Service not ready".
  3. Return an isolated HTTP client for the tester. The client is created as a module-level singleton (lazy initialization) with its own connection pool (maximum 10 connections). Timeout is taken from application settings.
  4. The client MUST be properly closed on application shutdown. Add closure to lifespan or use a finalizer.
- **Isolation rationale:** Reusing a single `httpx.AsyncClient` from the adapter for both TesterService and health checks creates shared state. If TesterService sends a heavy request with a large body, it may exhaust the connection pool for health checks and vice versa. An isolated client with its own connection pool prevents cascading failures.
- **Lifecycle:** The client is created on first factory call (lazy), reused between requests (module-level singleton), closed on application shutdown (via lifespan or atexit).

### 2.11. Factory: get_tester_service

- **Dependencies:** ProviderRepository (from get_provider_repo), httpx.AsyncClient (from get_tester_http_client)
- **Returns:** TesterService
- **Logic:**
  1. Get `provider_repo` via DI (Depends on `get_provider_repo`).
  2. Get `http_client` via DI (Depends on `get_tester_http_client`).
  3. Create and return a `TesterService(provider_repo=provider_repo, http_client=http_client)` instance.
- **Defensive check:** If `provider_repo` is not a `ProviderRepository` instance — create a fallback with `session=None` (similar to existing factories).

---

## 3. Dependency Graph

Root dependency — AsyncSession (from get_db_session). It branches into:

- **ProviderRepository** → used in ChatService, PolicyService, and TesterService.
- **PolicyRepository** → used in PolicyService.
- **LogRepository** → used in LogService and WebhookService. LogService, in turn, is used in ChatService, PolicyService, and WebhookService.
- **PortkeyAdapter** (stateless singleton, no session dependency) → used in ChatService, PolicyService, get_http_client, and get_tester_http_client.
- **httpx.AsyncClient (primary)** → used in ProviderService (health check).
- **httpx.AsyncClient (isolated)** → used in TesterService.

---

## 4. Error Handling

- Dependency creation errors (e.g., DB unavailable) are propagated as HTTP 500.
- FastAPI automatically handles exceptions from `Depends` functions.
- If the adapter is not initialized when calling `get_http_client` or `get_tester_http_client` — HTTP 503 "Service not ready".

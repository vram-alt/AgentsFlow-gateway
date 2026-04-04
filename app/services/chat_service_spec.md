# Specification: Chat Service (ChatService)

> **Implementation file:** `chat_service.py`  
> **Layer:** Services / Use Cases  
> **Responsibility:** Orchestrating the full cycle of sending a prompt to an LLM via an adapter

---

## 1. General Rules

- The service is **unaware** of specific adapters — it works through the `GatewayProvider` contract.
- The service is **unaware** of HTTP/FastAPI — it accepts and returns domain DTOs.
- Provider credentials are fetched from the database **on every call** (hot key rotation).
- Logging is delegated to `LogService` (background task).

---

## 2. Class: ChatService

### Dependencies (via constructor)

| Parameter           | Type                 | Description                                 |
|---------------------|----------------------|---------------------------------------------|
| `provider_repo`     | `ProviderRepository` | Repository for fetching credentials         |
| `log_service`       | `LogService`         | Logging service                             |
| `adapter`           | `GatewayProvider`    | Provider adapter (injected)                 |

---

## 3. Method: send_chat_message

### Interface Description

- **Async method** accepting the following parameters:
  - `model` (string, required) — LLM model identifier.
  - `messages` (list of dicts, required) — conversation messages.
  - `provider_name` (string, default "portkey") — provider name.
  - `temperature` (float or absent) — generation temperature.
  - `max_tokens` (integer or absent) — maximum number of tokens.
  - `guardrail_ids` (list of strings or absent) — Guardrail policy identifiers.
- **Returns:** UnifiedResponse on success or GatewayError on error.

### Step-by-Step Logic

1. **Generate Trace ID:**
   - Create `trace_id = str(uuid.uuid4())`.

2. **Fetch provider credentials:**
   - Call `provider_repo.get_active_by_name(provider_name)`.
   - If provider not found or inactive → return `GatewayError(error_code="AUTH_FAILED", message="Provider not found or deactivated")`.
   - Extract `api_key` and `base_url` from the provider record.

3. **Build UnifiedPrompt:**
   - Create `UnifiedPrompt` from input parameters:
     - `trace_id` — generated UUID.
     - `model` — provided model.
     - `messages` — list of `MessageItem` from provided dicts.
     - `temperature`, `max_tokens` — if provided.
     - `guardrail_ids` — if provided, otherwise empty list.

4. **Send via adapter:**
   - Call `adapter.send_prompt(prompt, api_key, base_url)`.
   - Receive result: `UnifiedResponse` or `GatewayError`.

5. **Logging (asynchronous):**
   - Regardless of result — call `log_service.log_chat_request(...)`:
     - `trace_id` — correlation ID.
     - `prompt` — sent prompt (serialized).
     - `response` — received response or error (serialized).
   - Logging **must not** block the response to the user.

6. **Return result:**
   - Return `UnifiedResponse` or `GatewayError` to the caller.

---

## 4. Error Handling

| Scenario                              | Action                                            |
|---------------------------------------|---------------------------------------------------|
| Provider not found in DB              | `GatewayError(error_code="AUTH_FAILED")`          |
| DB error when fetching provider       | `GatewayError(error_code="UNKNOWN")`              |
| Adapter returned `GatewayError`       | Pass through as-is + log                          |
| Unexpected exception                  | Wrap in `GatewayError(error_code="UNKNOWN")`      |
| Logging error                         | Suppress (does not affect user response)          |

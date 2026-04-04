# Specification: Contracts (Abstract Interfaces)

> **Implementation file:** `gateway_provider.py`  
> **Layer:** Domain (pure core)  
> **Responsibility:** Defining abstract interfaces for provider adapters

---

## 1. General Rules

- Contracts are implemented as abstract classes (`abc.ABC` + `abc.abstractmethod`).
- A contract **does not import** anything from the `infrastructure`, `services`, or `api` layers.
- A contract operates **exclusively** with domain DTOs: `UnifiedPrompt`, `UnifiedResponse`, `GatewayError`.
- All methods are **asynchronous** (`async def`).

---

## 2. Interface: GatewayProvider

### Purpose

The base contract that every external LLM provider adapter must implement.
Ensures complete isolation of the core from vendor-specific logic.

### Properties

| Property        | Type   | Description                                     |
|-----------------|--------|-------------------------------------------------|
| `provider_name` | `str`  | Unique provider name (e.g., "portkey")          |

### Methods

#### 2.1. `send_prompt(prompt: UnifiedPrompt, api_key: str, base_url: str) -> UnifiedResponse | GatewayError`

**Purpose:** Send a request to the LLM provider.

**Step-by-step logic (implemented in the adapter):**

1. Accept `UnifiedPrompt` and credentials (`api_key`, `base_url`).
2. Transform `UnifiedPrompt` into the vendor-specific request format.
3. Execute an asynchronous HTTP call to the provider API with a timeout.
4. On success — transform the provider response into `UnifiedResponse`.
5. On error — return `GatewayError` with the appropriate error code.

**Parameters:**

| Parameter  | Type             | Description                                     |
|------------|------------------|-------------------------------------------------|
| `prompt`   | `UnifiedPrompt`  | Standardized request                            |
| `api_key`  | `str`            | Current API key (from DB, not cached)           |
| `base_url` | `str`            | Base URL of the provider API                    |

**Returns:** `UnifiedResponse` on success, `GatewayError` on error.

---

#### 2.2. `create_guardrail(config: dict, api_key: str, base_url: str) -> dict | GatewayError`

**Purpose:** Create a security policy (Guardrail) on the provider side.

**Step-by-step logic:**

1. Accept the JSON policy configuration and credentials.
2. Send a POST request to the provider API to create the Guardrail.
3. On success — return a dict with `remote_id` and metadata.
4. On error — return `GatewayError`.

**Parameters:**

| Parameter  | Type   | Description                                     |
|------------|--------|-------------------------------------------------|
| `config`   | `dict` | JSON body of the Guardrail configuration        |
| `api_key`  | `str`  | Current API key                                 |
| `base_url` | `str`  | Base URL of the provider API                    |

**Returns:** `dict` with key `remote_id` on success, `GatewayError` on error.

---

#### 2.3. `update_guardrail(remote_id: str, config: dict, api_key: str, base_url: str) -> dict | GatewayError`

**Purpose:** Update an existing security policy on the provider side.

**Step-by-step logic:**

1. Accept the `remote_id` of the existing policy, the new configuration, and credentials.
2. Send a PUT request to the provider API.
3. On success — return updated metadata.
4. On error — return `GatewayError`.

**Parameters:**

| Parameter   | Type   | Description                                     |
|-------------|--------|-------------------------------------------------|
| `remote_id` | `str`  | Vendor-side policy identifier                   |
| `config`    | `dict` | New JSON configuration body                     |
| `api_key`   | `str`  | Current API key                                 |
| `base_url`  | `str`  | Base URL of the provider API                    |

**Returns:** `dict` on success, `GatewayError` on error.

---

#### 2.4. `delete_guardrail(remote_id: str, api_key: str, base_url: str) -> bool | GatewayError`

**Purpose:** Delete a security policy on the provider side.

**Step-by-step logic:**

1. Accept `remote_id` and credentials.
2. Send a DELETE request to the provider API.
3. On success — return `True`.
4. On error — return `GatewayError`.

**Returns:** `True` on success, `GatewayError` on error.

---

#### 2.5. `list_guardrails(api_key: str, base_url: str) -> list[dict] | GatewayError`

**Purpose:** Retrieve the list of all security policies from the provider (for synchronization).

**Step-by-step logic:**

1. Accept credentials.
2. Send a GET request to the provider API.
3. On success — return a list of dicts with policy data.
4. On error — return `GatewayError`.

**Returns:** `list[dict]` on success, `GatewayError` on error.

---

## 3. Error Handling

- All methods **never raise exceptions** to the caller.
- Any error (network, timeout, invalid response) is wrapped in `GatewayError`.
- This allows upstream layers to handle errors uniformly via return type checking.

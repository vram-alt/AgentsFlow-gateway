# Specification: Security Policy Service (PolicyService)

> **Implementation file:** `policy_service.py`  
> **Layer:** Services / Use Cases  
> **Responsibility:** CRUD operations on policies (Guardrails) with bidirectional synchronization with the provider cloud

---

## 1. General Rules

- The service coordinates work between `PolicyRepository` (local DB) and `GatewayProvider` (vendor cloud).
- Any policy change must be synchronized: cloud first, then DB.
- On cloud synchronization error — the operation is cancelled, DB is not modified.
- Provider credentials are fetched from `ProviderRepository` on every call.

---

## 2. Class: PolicyService

### Dependencies (via constructor)

| Parameter           | Type                 | Description                                 |
|---------------------|----------------------|---------------------------------------------|
| `policy_repo`       | `PolicyRepository`   | Policy repository                           |
| `provider_repo`     | `ProviderRepository` | Provider repository (for keys)              |
| `adapter`           | `GatewayProvider`    | Provider adapter                            |
| `log_service`       | `LogService`         | Logging service                             |

---

## 3. Method: create_policy

### Interface Description

- **Async method** accepting the following parameters:
  - `name` (string, required) — policy name.
  - `body` (dict, required) — JSON body of the Guardrail configuration.
  - `provider_name` (string, default "portkey") — provider name.
- **Returns:** Policy domain entity on success or GatewayError on error.

### Step-by-Step Logic

1. **Fetch provider credentials** from `provider_repo.get_active_by_name(provider_name)`.
   - If not found → `GatewayError(error_code="AUTH_FAILED")`.

2. **Send configuration to cloud** via `adapter.create_guardrail(body, api_key, base_url)`.
   - On error → return `GatewayError` (DB is not modified).

3. **Save to local DB** via `policy_repo.create(name, body, remote_id, provider_id)`.
   - `remote_id` — from the cloud response.

4. **Return** the `Policy` domain entity.

---

## 4. Method: update_policy

### Interface Description

- **Async method** accepting the following parameters:
  - `policy_id` (integer, required) — policy identifier in DB.
  - `name` (string or absent) — new name (if changing).
  - `body` (dict or absent) — new JSON body (if changing).
- **Returns:** Policy domain entity on success or GatewayError on error.

### Step-by-Step Logic

1. **Find the policy** in DB by `policy_id`.
   - If not found → `GatewayError(error_code="VALIDATION_ERROR", message="Policy not found")`.

2. **If `body` changed** and `remote_id` exists:
   - Fetch provider credentials.
   - Send update to cloud via `adapter.update_guardrail(remote_id, body, ...)`.
   - On error → return `GatewayError` (DB is not modified).

3. **Update the DB record** via `policy_repo.update(policy_id, **changed_fields)`.

4. **Return** the updated `Policy` entity.

---

## 5. Method: delete_policy

### Interface Description

- **Async method** accepting one parameter: `policy_id` (integer — policy identifier in DB).
- **Returns:** boolean True on success or GatewayError on error.

### Step-by-Step Logic

1. **Find the policy** in DB by `policy_id`.
   - If not found → `GatewayError`.

2. **If `remote_id` exists:**
   - Fetch provider credentials.
   - Delete in cloud via `adapter.delete_guardrail(remote_id, ...)`.
   - On cloud error → return `GatewayError` (DB is not modified).

3. **Soft Delete in DB** via `policy_repo.soft_delete(policy_id)`.

4. **Return** `True`.

---

## 6. Method: list_policies

### Interface Description

- **Async method** accepting one parameter: `only_active` (boolean, default True) — activity filter.
- **Returns:** list of Policy domain entities.

### Step-by-Step Logic

1. Call `policy_repo.list_all(only_active=only_active)`.
2. Convert ORM models to `Policy` domain entities.
3. Return the list.

---

## 7. Method: sync_policies_from_provider

### Purpose

Load existing policies from the provider cloud and synchronize with the local DB.
Triggered by the "Sync" button in the UI.

### Interface Description

- **Async method** accepting one parameter: `provider_name` (string, default "portkey") — provider name for synchronization.
- **Returns:** dict with a synchronization report.

### Step-by-Step Logic

1. **Fetch provider credentials** from `provider_repo`.

2. **Request the policy list from cloud** via `adapter.list_guardrails(api_key, base_url)`.
   - On error → return `GatewayError`.

3. **For each policy from cloud:**
   - Check if a DB record with that `remote_id` exists via `policy_repo.get_by_remote_id(remote_id)`.
   - **If not found** → create a new record via `policy_repo.create(...)`.
   - **If found** → update `name` and `body` if they differ.

4. **Return the synchronization report** — a dict with the following keys:

   | Key             | Type    | Description                       |
   |-----------------|---------|-----------------------------------|
   | `created`       | integer | Number of new policies            |
   | `updated`       | integer | Number of updated policies        |
   | `unchanged`     | integer | Number of unchanged policies      |
   | `total_remote`  | integer | Total policies in provider cloud  |

---

## 8. Error Handling

| Scenario                              | Action                                            |
|---------------------------------------|---------------------------------------------------|
| Provider not found                    | `GatewayError(error_code="AUTH_FAILED")`          |
| Cloud error on create/update          | `GatewayError` — DB is not modified               |
| DB error                              | `GatewayError(error_code="UNKNOWN")`              |
| Policy not found by ID               | `GatewayError(error_code="VALIDATION_ERROR")`     |
| Error syncing a single policy         | Skip, continue with remaining, log the error      |

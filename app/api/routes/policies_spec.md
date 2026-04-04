# Specification: Security Policies Router (policies.py)

> **Implementation file:** `policies.py`  
> **Layer:** API / Delivery  
> **Responsibility:** HTTP handlers for CRUD operations on policies (Guardrails) and cloud synchronization

---

## 1. General Rules

- Routes are thin wrappers: accept an HTTP request, call the service, return an HTTP response.
- Business logic is **prohibited** in routes — only routing and transformation.
- All dependencies are obtained via FastAPI Depends.
- Pydantic schemas for request/response are defined in this file.

---

## 2. Router

**Prefix:** `/api/policies`  
**Tags:** "Policies"  
**Protection:** HTTP Basic Auth.

---

## 3. Endpoint: GET /api/policies/

### Purpose

List all active policies.

### Step-by-Step Logic

1. Call policy_service.list_policies().
2. Return HTTP 200 with the list of policies.

---

## 4. Endpoint: POST /api/policies/

### Purpose

Create a new policy (with cloud synchronization).

### Request Body (PolicyCreateRequest schema)

| Field           | Type    | Required | Default      | Description                 |
|-----------------|---------|----------|--------------|-----------------------------|
| `name`          | string  | Yes      | —            | Policy name                 |
| `body`          | dict    | Yes      | —            | JSON configuration body     |
| `provider_name` | string  | No       | "portkey"    | Provider name               |

### Step-by-Step Logic

1. Call policy_service.create_policy(name, body, provider_name).
2. On success → HTTP 201 with policy data.
3. On GatewayError → HTTP with corresponding status.

---

## 5. Endpoint: PUT /api/policies/{policy_id}

### Purpose

Update a policy.

### Request Body (PolicyUpdateRequest schema)

| Field  | Type             | Required | Description                       |
|--------|------------------|----------|-----------------------------------|
| `name` | string or null   | No       | New name (if changing)            |
| `body` | dict or null     | No       | New JSON body (if changing)       |

---

## 6. Endpoint: DELETE /api/policies/{policy_id}

### Purpose

Soft Delete a policy (with cloud deletion).

### Step-by-Step Logic

1. Call policy_service.delete_policy(policy_id).
2. On success → HTTP 200 with JSON body containing a status field with value "deleted".
3. On error → HTTP with corresponding status.

---

## 7. Endpoint: POST /api/policies/sync

### Purpose

Synchronize policies from the provider cloud ("Sync" button).

### Request Body (SyncRequest schema)

| Field           | Type   | Required | Default      | Description    |
|-----------------|--------|----------|--------------|----------------|
| `provider_name` | string | No       | "portkey"    | Provider name  |

### Step-by-Step Logic

1. Call policy_service.sync_policies_from_provider(provider_name).
2. Return HTTP 200 with the synchronization report.

---

## 8. Error Handling

| HTTP Status | When                                     |
|-------------|------------------------------------------|
| 200         | Successful operation                     |
| 201         | Successful resource creation             |
| 401         | Invalid token / unauthorized             |
| 404         | Resource not found                       |
| 422         | Invalid JSON (Pydantic)                  |
| 500         | Internal server error                    |
| 502         | Provider error                           |

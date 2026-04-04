# Specification: Webhook Service (WebhookService)

> **Implementation file:** `webhook_service.py`  
> **Layer:** Services / Use Cases  
> **Responsibility:** Processing incoming webhook reports from providers (Mode B — Passive Listener)

---

## 1. General Rules

- The service processes incoming JSON reports about security incidents (Guardrail).
- Each report is linked to the original request via `trace_id`.
- The service is **unaware** of HTTP/FastAPI — it accepts raw data.
- Security token validation (`X-Webhook-Secret`) is the responsibility of the `api/` layer.

---

## 2. Class: WebhookService

### Dependencies (via constructor)

| Parameter       | Type             | Description                                 |
|-----------------|------------------|---------------------------------------------|
| `log_service`   | `LogService`     | Logging service                             |
| `log_repo`      | `LogRepository`  | Log repository (for trace_id verification)  |

---

## 3. Incoming Payload Constraints (DoS Protection)

To prevent denial-of-service attacks via oversized or deeply nested JSON bodies, the following checks must be implemented at the route level (webhook.py) **before** passing data to the service:

- **Maximum request body size:** 1 megabyte. If the Content-Length header exceeds the limit or the actual body size exceeds the limit — immediately return HTTP 413 Payload Too Large.
- **Maximum JSON nesting depth:** 10 levels. If deeper nesting is detected — return HTTP 422 with a description of the constraint.
- These checks are performed at the API layer; the service receives already validated data.

---

## 4. Method: process_guardrail_incident

### Purpose

Process an incoming webhook report about a Guardrail trigger.

### Interface Description

- **Async method** accepting one parameter: `payload` (dict — incoming webhook request body).
- **Returns:** dict with processing confirmation.

### Step-by-Step Logic

1. **Extract trace_id from payload:**
   - Look for `trace_id` at the root of payload.
   - If `trace_id` is absent or empty — look in `payload.get("metadata", {}).get("trace_id")`.
   - If still not found — generate a new UUID and mark as `"trace_id_source": "generated"`.

2. **Validate trace_id format:**
   - Verify that `trace_id` conforms to UUID v4 format.
   - If invalid format — use as-is, but add a warning to the log.

3. **Check linkage to original request:**
   - Call `log_repo.get_by_trace_id(trace_id)`.
   - If records with `event_type="chat_request"` are found — the incident is **linked** to a specific prompt.
   - If not found — the incident is **orphaned**, but is still recorded.

4. **Build incident record** — a dict with the following keys:
   - `original_webhook_body` — original webhook request body (from `payload` parameter)
   - `trace_id_source` — trace_id origin: `"webhook"` (if extracted from payload) or `"generated"` (if system-generated)
   - `linked_to_prompt` — boolean: whether the incident is linked to the original prompt
   - `processed_at` — current datetime in ISO 8601 format (UTC)

5. **Write to audit log:**
   - Call `log_service.log_guardrail_incident(trace_id, incident_payload)`.

6. **Return confirmation** — a dict with the following keys:
   - `status` — value `"accepted"`
   - `trace_id` — correlation identifier (used or generated)
   - `linked_to_prompt` — boolean: whether the incident is linked to the original prompt

---

## 5. Error Handling

| Scenario                        | Action                                            |
|---------------------------------|---------------------------------------------------|
| Empty payload                   | Return dict with status "rejected" and reason "empty payload" |
| Missing trace_id                | Generate a new one, record with annotation        |
| DB write error                  | Log the error, return dict with status "error"    |
| Invalid JSON in payload         | Handled at the api/ level (Pydantic)              |

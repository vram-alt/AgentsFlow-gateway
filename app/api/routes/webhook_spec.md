# Specification: Webhook Router (webhook.py)

> **Implementation file:** `webhook.py`  
> **Layer:** API / Delivery  
> **Responsibility:** HTTP handler for receiving incoming webhook reports from providers (Mode B)

---

## 1. General Rules

- The route is a thin wrapper: accepts an HTTP request, calls the service, returns an HTTP response.
- Business logic is **prohibited** in the route — only routing and transformation.
- All dependencies are obtained via FastAPI Depends.

---

## 2. Router

**Prefix:** `/api/webhook`  
**Tags:** "Webhook"  
**Protection:** Static token X-Webhook-Secret (NOT Basic Auth).

---

## 3. Endpoint: POST /api/webhook

### Purpose

Receive incoming webhook reports from providers (Mode B).

### Incoming Payload Constraints (DoS Protection)

To prevent denial-of-service attacks via oversized or deeply nested JSON bodies, the following checks must be implemented at this route level **before** passing data to the service:

- **Maximum request body size:** 1 megabyte. If the Content-Length header exceeds the limit or the actual body size exceeds the limit — immediately return HTTP 413 Payload Too Large.
- **Maximum JSON nesting depth:** 10 levels. If deeper nesting is detected — return HTTP 422 with a description of the constraint.

### Step-by-Step Logic

1. **Security token verification:**
   - Extract the X-Webhook-Secret header.
   - Compare with WEBHOOK_SECRET from environment variables.
   - If mismatch → immediately return HTTP 401 Unauthorized.

2. **Request body validation:**
   - Accept the JSON body as a dict (free-form structure).
   - If invalid JSON → HTTP 422.

3. **Processing:**
   - Call webhook_service.process_guardrail_incident(payload).
   - Return HTTP 200 with confirmation.

---

## 4. Error Handling

| HTTP Status | When                                     |
|-------------|------------------------------------------|
| 200         | Successful webhook processing            |
| 401         | Invalid X-Webhook-Secret                 |
| 413         | Maximum request body size exceeded       |
| 422         | Invalid JSON or nesting depth exceeded   |
| 500         | Internal server error                    |

# Specification: Chat Router (chat.py)

> **Implementation file:** `chat.py`  
> **Layer:** API / Delivery  
> **Responsibility:** HTTP handler for sending prompts to the LLM via the gateway (Mode A)

---

## 1. General Rules

- The route is a thin wrapper: accepts an HTTP request, calls the service, returns an HTTP response.
- Business logic is **prohibited** in the route — only routing and transformation.
- All dependencies are obtained via FastAPI Depends.
- Pydantic schemas for request/response are defined in this file.

---

## 2. Router

**Prefix:** `/api/chat`  
**Tags:** "Chat"

---

## 3. Endpoint: POST /api/chat/send

### Purpose

Send a prompt to the LLM via the gateway (Mode A).

### Request Body (ChatRequest schema)

| Field            | Type                                   | Required | Default       | Description                 |
|------------------|----------------------------------------|----------|---------------|-----------------------------|
| `model`          | string                                 | Yes      | —             | LLM model ID               |
| `messages`       | list of MessageItem                    | Yes      | —             | List of conversation messages|
| `provider_name`  | string                                 | No       | "portkey"     | Provider name               |
| `temperature`    | float or null                          | No       | null          | Generation temperature      |
| `max_tokens`     | integer or null                        | No       | null          | Max token count             |
| `guardrail_ids`  | list of strings                        | No       | empty list    | Guardrail policy IDs        |

### Step-by-Step Logic

1. Validate incoming JSON via Pydantic (automatic).
2. Call chat_service.send_chat_message(...).
3. If result is UnifiedResponse → return HTTP 200 with response body.
4. If result is GatewayError → return HTTP with corresponding status_code.
5. Delegate logging to BackgroundTasks.

### Response (HTTP 200, ChatResponse schema)

| Field               | Type                   | Description                       |
|---------------------|------------------------|-----------------------------------|
| `trace_id`          | string                 | Correlation UUID                  |
| `content`           | string                 | Model response text               |
| `model`             | string                 | Actual model that responded       |
| `usage`             | UsageInfo or null      | Token usage statistics            |
| `guardrail_blocked` | boolean                | Whether the request was blocked   |

### Response (HTTP 4xx/5xx, ErrorResponse schema)

| Field        | Type    | Description                           |
|--------------|---------|---------------------------------------|
| `trace_id`   | string  | Correlation UUID                      |
| `error_code` | string  | Error code (e.g., "TIMEOUT")          |
| `message`    | string  | Human-readable error description      |
| `details`    | dict    | Additional data (default empty)       |

### Protection

HTTP Basic Auth (via Depends).

---

## 4. Error Handling

| HTTP Status | When                                     |
|-------------|------------------------------------------|
| 200         | Successful submission and response       |
| 401         | Invalid token / unauthorized             |
| 422         | Invalid JSON (Pydantic)                  |
| 500         | Internal server error                    |
| 502         | Provider error                           |
| 504         | Provider timeout                         |

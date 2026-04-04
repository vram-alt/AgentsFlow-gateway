# Specification: Middleware

> **Implementation file:** `auth.py`  
> **Layer:** API / Delivery  
> **Responsibility:** Request authentication and authorization

---

## 1. General Rules

- Middleware is implemented as FastAPI `Depends` functions (not as ASGI middleware).
- Configuration (logins, passwords, tokens) is read from environment variables.
- Middleware **does not contain** business logic.

---

## 2. Module: auth.py

### 2.1. Function: verify_basic_auth

**Purpose:** Verify HTTP Basic Auth for protecting UI and API endpoints.

**Input:** Credentials (username, password) extracted from the `Authorization: Basic ...` HTTP header via FastAPI's built-in HTTP Basic mechanism.

**Return value:** String — the username on successful authentication.

**Step-by-step logic:**

1. Extract `username` and `password` from the `Authorization: Basic ...` HTTP header.
2. Compare with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from environment variables.
3. Use constant-time string comparison for timing attack protection.
4. If they match → reset the failed attempt counter for the given IP address and return `username`.
5. If they don't match → increment the failed attempt counter for the client IP address and return HTTP 401 with `WWW-Authenticate: Basic` header.

### 2.3. Brute-Force Protection Mechanism (Rate Limiting)

**Purpose:** Prevent brute-force attacks on authentication endpoints.

**Rules:**

- Implement an in-memory rate limiter tracking the number of failed authentication attempts per client IP address.
- Limit: maximum 5 failed attempts within a 60-second sliding window per IP address.
- On limit exceeded — immediately return HTTP 429 Too Many Requests **before** checking credentials (to avoid providing feedback on password validity).
- Records for blocked IPs automatically expire by TTL (60 seconds from the first failed attempt in the window).
- On successful authentication — reset the counter for the given IP.
- The rate limiter applies to both `verify_basic_auth` and `verify_webhook_secret` functions.

### 2.2. Function: verify_webhook_secret

**Purpose:** Verify a static token for the webhook endpoint (Anti-Spam).

**Input:** Value of the `X-Webhook-Secret` HTTP header (required header).

**Return value:** Boolean `True` on successful verification.

**Step-by-step logic:**

1. Extract the `X-Webhook-Secret` header value.
2. Compare with `WEBHOOK_SECRET` from environment variables.
3. Use constant-time string comparison for timing attack protection.
4. If they match → return `True`.
5. If they don't match → return HTTP 401 with message `"Invalid webhook secret"`.

---

## 3. Error Handling

| Scenario                        | Action                                            |
|---------------------------------|---------------------------------------------------|
| Missing Auth header             | HTTP 401 with `WWW-Authenticate: Basic`           |
| Invalid credentials             | HTTP 401 with `WWW-Authenticate: Basic`           |
| Attempt limit exceeded (brute-force) | HTTP 429 Too Many Requests                   |
| Missing X-Webhook-Secret        | HTTP 422 (FastAPI automatic — Header required)    |
| Invalid webhook secret          | HTTP 401 `Invalid webhook secret`                 |

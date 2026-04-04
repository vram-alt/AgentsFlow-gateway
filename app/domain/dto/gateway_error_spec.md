# Specification: DTO GatewayError (gateway_error.py)

> **Implementation file:** `gateway_error.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Standardized representation of an error that occurred during provider interaction

---

## 1. General Rules

- The DTO is an **immutable** (frozen) Pydantic model for transferring data between layers.
- The model must be configured as immutable (frozen) via the Pydantic V2 configuration mechanism.
- GatewayError is used as a return value (not as an exception) for uniform error handling via type checking.

---

## 2. DTO: GatewayError

### Purpose

Standardized representation of an error that occurred during provider interaction.

### Fields

| Field          | Type             | Required | Default        | Description                                       |
|----------------|------------------|----------|----------------|---------------------------------------------------|
| `trace_id`     | string           | Yes      | —              | UUID v4 correlation identifier                    |
| `error_code`   | string           | Yes      | —              | Error code (e.g., "TIMEOUT", "AUTH_FAILED")       |
| `message`      | string           | Yes      | —              | Human-readable error description                  |
| `status_code`  | integer          | No       | 500            | HTTP status code                                  |
| `provider_name`| string or None   | No       | None           | Name of the provider that caused the error        |
| `details`      | dict             | No       | empty dict     | Additional data for debugging                     |

### Standard Error Codes (Constants)

| Code Constant      | Description                                           |
|--------------------|-------------------------------------------------------|
| TIMEOUT            | Provider response timeout exceeded                    |
| AUTH_FAILED        | Authentication error (invalid API key)                |
| PROVIDER_ERROR     | Internal error on the provider side                   |
| VALIDATION_ERROR   | Invalid input data                                    |
| RATE_LIMITED       | Request rate limit exceeded                           |
| UNKNOWN            | Unknown error                                         |

### Validation

- `trace_id`: UUID v4 format.
- `error_code`: non-empty string.
- `message`: non-empty string.
- `status_code`: in range [400, 599].

---

## 3. Error Handling

A standard pydantic.ValidationError is raised on invalid data.
Transforming errors into HTTP responses is the responsibility of the api/ layer.

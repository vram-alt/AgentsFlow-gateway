# Specification: DTO UnifiedResponse (unified_response.py)

> **Implementation file:** `unified_response.py`  
> **Layer:** Domain (pure core, zero external dependencies except Pydantic)  
> **Responsibility:** Standardized representation of a response from an LLM provider

---

## 1. General Rules

- The DTO is an **immutable** (frozen) Pydantic model for transferring data between layers.
- Adapters are required to transform vendor-specific formats into this DTO and back.
- The system core works **exclusively** with this DTO, never with vendor formats.
- The model must be configured as immutable (frozen) via the Pydantic V2 configuration mechanism.

---

## 2. Nested Model: UsageInfo

| Field              | Type    | Required | Description                 |
|--------------------|---------|----------|-----------------------------|
| `prompt_tokens`    | integer | Yes      | Number of prompt tokens     |
| `completion_tokens`| integer | Yes      | Number of completion tokens |
| `total_tokens`     | integer | Yes      | Total number of tokens      |

### UsageInfo Validation

- All fields: non-negative integers.

---

## 3. DTO: UnifiedResponse

### Purpose

Standardized representation of an LLM provider response that the adapter returns to the core.

### Fields

| Field               | Type                   | Required | Default      | Description                                       |
|---------------------|------------------------|----------|--------------|---------------------------------------------------|
| `trace_id`          | string                 | Yes      | —            | UUID v4 (same as in the request)                  |
| `content`           | string                 | Yes      | —            | Model response text                               |
| `model`             | string                 | Yes      | —            | Actual model that responded                       |
| `usage`             | UsageInfo or None      | No       | None         | Token usage statistics                            |
| `provider_raw`      | dict                   | No       | empty dict   | Raw provider response (for debugging)             |
| `guardrail_blocked` | boolean                | No       | False        | Whether the request was blocked by Guardrail      |
| `guardrail_details` | dict or None           | No       | None         | Block details (if applicable)                     |

### Validation

- `trace_id`: UUID v4 format.
- `content`: may be an empty string (if blocked by Guardrail).

---

## 4. Error Handling

A standard pydantic.ValidationError is raised on invalid data.
Transforming errors into HTTP responses is the responsibility of the api/ layer.

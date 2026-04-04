"""
Domain entity Policy — Pydantic V2 models.

Schemas:
  - PolicyBase: shared fields + validation
  - PolicyCreate: policy creation
  - PolicyUpdate: partial update (PATCH)
  - Policy: complete entity with id and timestamps
"""

from __future__ import annotations

import datetime
import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.utils.time import _utc_now


# Type for name with automatic strip and length constraints
StrippedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
OptionalStrippedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class PolicyBase(BaseModel):
    """Base schema with shared fields and validation."""

    name: StrippedName
    body: dict[str, Any]
    remote_id: str | None = Field(default=None, min_length=1)
    provider_id: int | None = None
    is_active: bool = True

    @field_validator("body", mode="before")
    @classmethod
    def body_coerce_and_validate(cls, v: Any) -> dict[str, Any]:
        """Accepts dict or JSON string; rejects empty dict.
        [SRE_MARKER] — an empty policy must not pass validation.
        """
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                raise ValueError("body must be a valid JSON string or dict")
        if not isinstance(v, dict):
            raise ValueError("body must be a dict")
        if not v:
            raise ValueError("body must contain at least one key")
        return v


class PolicyCreate(PolicyBase):
    """Schema for creating a policy (inherits all PolicyBase validation)."""


class PolicyUpdate(BaseModel):
    """Schema for partial update (PATCH). All fields are optional."""

    name: OptionalStrippedName | None = None
    body: dict[str, Any] | None = None
    is_active: bool | None = None
    remote_id: str | None = Field(default=None, min_length=1)
    provider_id: int | None = None

    @field_validator("body", mode="before")
    @classmethod
    def body_coerce_and_validate(cls, v: Any) -> dict[str, Any] | None:
        """[SRE_MARKER] — updating a policy with an empty body will nullify the guardrail."""
        if v is None:
            return v
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                raise ValueError("body must be a valid JSON string or dict")
        if not isinstance(v, dict):
            raise ValueError("body must be a dict")
        if not v:
            raise ValueError("body must contain at least one key")
        return v


class Policy(PolicyBase):
    """Complete domain entity with id and timestamps."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    created_at: datetime.datetime = Field(default_factory=_utc_now)
    updated_at: datetime.datetime = Field(default_factory=_utc_now)

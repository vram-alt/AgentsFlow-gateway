"""Domain entity Provider — Pydantic models for an LLM provider."""

from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.utils.time import _utc_now


class ProviderBase(BaseModel):
    """Base schema with shared fields and validation."""

    name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=1)
    base_url: str = Field(...)
    is_active: bool = Field(default=True)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


class ProviderCreate(ProviderBase):
    """Schema for creating a provider (all required fields from Base)."""


class ProviderUpdate(BaseModel):
    """Schema for partial update (PATCH). All fields are optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    api_key: Optional[str] = Field(default=None, min_length=1)
    base_url: Optional[str] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


class Provider(ProviderBase):
    """Complete domain entity with id and timestamps."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(default=None)
    created_at: datetime.datetime = Field(default_factory=_utc_now)
    updated_at: datetime.datetime = Field(default_factory=_utc_now)

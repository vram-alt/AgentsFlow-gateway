"""
Доменная сущность Policy — Pydantic V2 модели.

Схемы:
  - PolicyBase: общие поля + валидация
  - PolicyCreate: создание политики
  - PolicyUpdate: частичное обновление (PATCH)
  - Policy: полная сущность с id и датами
"""

from __future__ import annotations

import datetime
import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


def _utc_now() -> datetime.datetime:
    """Фабрика: текущее UTC-время (timezone-aware)."""
    return datetime.datetime.now(datetime.timezone.utc)


# Тип для name с автоматическим strip и ограничениями длины
StrippedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
OptionalStrippedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class PolicyBase(BaseModel):
    """Базовая схема с общими полями и валидацией."""

    name: StrippedName
    body: dict[str, Any]
    remote_id: str | None = Field(default=None, min_length=1)
    provider_id: int | None = None
    is_active: bool = True

    @field_validator("body", mode="before")
    @classmethod
    def body_coerce_and_validate(cls, v: Any) -> dict[str, Any]:
        """Принимает dict или JSON-строку; отклоняет пустой dict.
        [SRE_MARKER] — пустая политика не должна пройти валидацию.
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
    """Схема для создания политики (наследует всю валидацию PolicyBase)."""


class PolicyUpdate(BaseModel):
    """Схема для частичного обновления (PATCH). Все поля опциональны."""

    name: OptionalStrippedName | None = None
    body: dict[str, Any] | None = None
    is_active: bool | None = None
    remote_id: str | None = Field(default=None, min_length=1)
    provider_id: int | None = None

    @field_validator("body", mode="before")
    @classmethod
    def body_coerce_and_validate(cls, v: Any) -> dict[str, Any] | None:
        """[SRE_MARKER] — обновление политики пустым body обнулит guardrail."""
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
    """Полная доменная сущность с id и временными метками."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    created_at: datetime.datetime = Field(default_factory=_utc_now)
    updated_at: datetime.datetime = Field(default_factory=_utc_now)

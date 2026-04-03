"""
Конфигурация приложения через Pydantic Settings.

Минимальная реализация для поддержки models.py (encryption_key).
"""

from __future__ import annotations

import base64
import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Централизованная конфигурация, читаемая из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "sqlite+aiosqlite:///./gateway.db"
    admin_username: str
    admin_password: str
    webhook_secret: str
    encryption_key: str
    external_http_timeout: int = 30

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("database_url")
    @classmethod
    def _database_url_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("database_url must not be empty (пустая строка запрещена)")
        return v

    @field_validator("admin_username")
    @classmethod
    def _admin_username_not_trivial(cls, v: str) -> str:
        trivial = {"admin", "root", "administrator"}
        if v.lower() in trivial:
            raise ValueError(
                "admin_username is trivial/predictable — "
                "значения admin, root, administrator запрещены"
            )
        return v

    @field_validator("admin_password")
    @classmethod
    def _admin_password_complexity(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("admin_password must be at least 12 символов length")
        if not re.search(r"\d", v):
            raise ValueError("admin_password must contain at least one digit (цифру)")
        if not re.search(r"[^a-zA-Z0-9]", v):
            raise ValueError(
                "admin_password must contain at least one special character (спецсимвол)"
            )
        return v

    @field_validator("webhook_secret")
    @classmethod
    def _webhook_secret_min_length(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("webhook_secret must be at least 16 символов length")
        return v

    @field_validator("encryption_key")
    @classmethod
    def _encryption_key_fernet_format(cls, v: str) -> str:
        if len(v) != 44:
            raise ValueError(
                "encryption_key must be exactly 44 characters (Fernet/base64 key format)"
            )
        try:
            decoded = base64.urlsafe_b64decode(v)
            # Fernet key: 32 bytes encoded → 44 base64 chars
            if len(decoded) != 32:
                raise ValueError(
                    "encryption_key base64 decodes to wrong length — "
                    "expected Fernet key (32 bytes)"
                )
        except Exception as exc:
            if "encryption_key" in str(exc):
                raise
            raise ValueError(
                "encryption_key is not valid base64 — "
                "expected Fernet key format (44 base64 characters)"
            ) from exc
        return v

    @field_validator("external_http_timeout")
    @classmethod
    def _timeout_in_range(cls, v: int) -> int:
        if v < 5 or v > 120:
            raise ValueError(
                "external_http_timeout must be in range [5, 120] (диапазон)"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает кэшированный (синглтон) экземпляр Settings."""
    return Settings()

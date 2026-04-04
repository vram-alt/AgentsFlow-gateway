"""
TDD Red phase: тесты для app/config.py

Проверяют:
- Загрузку переменных окружения через Pydantic Settings
- Значения по умолчанию (database_url, external_http_timeout)
- Обязательность полей (admin_username, admin_password, webhook_secret, encryption_key)
- Валидацию: тривиальные имена, сложность пароля, длина webhook_secret,
  формат Fernet-ключа, диапазон timeout
- Синглтон-поведение get_settings()
- Каст типов (external_http_timeout → int)

Specification: app/config_spec.md
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Fixtures: валидные значения окружения
# ---------------------------------------------------------------------------

# Валидный Fernet-ключ: 32 байта → base64 = 44 символа
_VALID_FERNET_KEY: str = base64.urlsafe_b64encode(b"0" * 32).decode()


def _valid_env() -> dict[str, str]:
    """Минимальный набор переменных окружения, проходящий все валидаторы."""
    return {
        "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
        "ADMIN_USERNAME": "operator_jane",
        "ADMIN_PASSWORD": "Str0ng!Pass#2024",
        "WEBHOOK_SECRET": "wh_secret_long_enough_16",
        "ENCRYPTION_KEY": _VALID_FERNET_KEY,
        "EXTERNAL_HTTP_TIMEOUT": "30",
    }


@pytest.fixture()
def valid_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Устанавливает валидные переменные окружения и возвращает словарь."""
    env = _valid_env()
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Переключает рабочую директорию в tmp, чтобы .env не подхватывался."""
    monkeypatch.chdir(tmp_path)


# =========================================================================
# 1. Успешная загрузка с полным набором переменных
# =========================================================================


class TestSettingsHappyPath:
    """Проверяем, что Settings корректно читает все поля из окружения."""

    def test_all_fields_loaded(self, valid_env: dict[str, str]) -> None:
        """Все поля загружаются из переменных окружения."""
        settings = Settings(_env_file=None)
        assert settings.database_url == valid_env["DATABASE_URL"]
        assert settings.admin_username == valid_env["ADMIN_USERNAME"]
        assert settings.admin_password == valid_env["ADMIN_PASSWORD"]
        assert settings.webhook_secret == valid_env["WEBHOOK_SECRET"]
        assert settings.encryption_key == valid_env["ENCRYPTION_KEY"]
        assert settings.external_http_timeout == int(valid_env["EXTERNAL_HTTP_TIMEOUT"])

    def test_external_http_timeout_is_int(self, valid_env: dict[str, str]) -> None:
        """external_http_timeout кастуется в int из строки окружения."""
        settings = Settings(_env_file=None)
        assert isinstance(settings.external_http_timeout, int)
        assert settings.external_http_timeout == 30


# =========================================================================
# 2. Значения по умолчанию
# =========================================================================


class TestDefaults:
    """Проверяем значения по умолчанию для необязательных полей."""

    def test_database_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_url по умолчанию = sqlite+aiosqlite:///./gateway.db."""
        env = _valid_env()
        env.pop("DATABASE_URL")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        settings = Settings(_env_file=None)
        assert settings.database_url == "sqlite+aiosqlite:///./gateway.db"

    def test_external_http_timeout_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """external_http_timeout по умолчанию = 30."""
        env = _valid_env()
        env.pop("EXTERNAL_HTTP_TIMEOUT")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("EXTERNAL_HTTP_TIMEOUT", raising=False)

        settings = Settings(_env_file=None)
        assert settings.external_http_timeout == 30


# =========================================================================
# 3. Обязательные поля — отсутствие вызывает ValidationError
# =========================================================================


class TestRequiredFields:
    """Обязательные поля без значения по умолчанию должны вызывать ValidationError."""

    @pytest.mark.parametrize(
        "missing_field",
        [
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "WEBHOOK_SECRET",
            "ENCRYPTION_KEY",
        ],
    )
    def test_missing_required_field_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_field: str,
    ) -> None:
        """Отсутствие обязательного поля → ValidationError при создании Settings."""
        env = _valid_env()
        env.pop(missing_field)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv(missing_field, raising=False)

        with pytest.raises(ValidationError):
            Settings(_env_file=None)


# =========================================================================
# 4. Валидация admin_username — запрет тривиальных значений
# =========================================================================


class TestAdminUsernameValidation:
    """[SRE_MARKER] Тривиальные имена пользователей запрещены."""

    @pytest.mark.parametrize(
        "trivial_name",
        ["admin", "root", "administrator"],
    )
    def test_trivial_username_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        trivial_name: str,
    ) -> None:
        """Тривиальные имена (admin, root, administrator) → ValidationError."""
        env = _valid_env()
        env["ADMIN_USERNAME"] = trivial_name
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(
            ValidationError, match="(?i)admin_username|trivial|predictable"
        ):
            Settings(_env_file=None)

    def test_valid_username_accepted(self, valid_env: dict[str, str]) -> None:
        """Нетривиальное имя пользователя проходит валидацию."""
        settings = Settings(_env_file=None)
        assert settings.admin_username == valid_env["ADMIN_USERNAME"]


# =========================================================================
# 5. Валидация admin_password — сложность пароля
# =========================================================================


class TestAdminPasswordValidation:
    """[SRE_MARKER] Пароль должен быть ≥12 символов, содержать цифру и спецсимвол."""

    def test_password_too_short(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Пароль короче 12 символов → ValidationError."""
        env = _valid_env()
        env["ADMIN_PASSWORD"] = "Sh0rt!pw"  # 8 символов
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)password|12|length|символ"):
            Settings(_env_file=None)

    def test_password_no_digit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Пароль без цифр → ValidationError."""
        env = _valid_env()
        env["ADMIN_PASSWORD"] = "NoDigitsHere!@#$"  # 16 символов, нет цифр
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)password|digit|цифр"):
            Settings(_env_file=None)

    def test_password_no_special_char(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Пароль без спецсимволов → ValidationError."""
        env = _valid_env()
        env["ADMIN_PASSWORD"] = "NoSpecial12345a"  # 15 символов, нет спецсимволов
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)password|special|спец"):
            Settings(_env_file=None)

    def test_valid_password_accepted(self, valid_env: dict[str, str]) -> None:
        """Пароль, соответствующий всем требованиям, проходит валидацию."""
        settings = Settings(_env_file=None)
        assert settings.admin_password == valid_env["ADMIN_PASSWORD"]


# =========================================================================
# 6. Валидация webhook_secret — минимум 16 символов
# =========================================================================


class TestWebhookSecretValidation:
    """[SRE_MARKER] webhook_secret должен быть ≥16 символов."""

    def test_webhook_secret_too_short(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """webhook_secret короче 16 символов → ValidationError."""
        env = _valid_env()
        env["WEBHOOK_SECRET"] = "short_secret"  # 12 символов
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)webhook|16|length|символ"):
            Settings(_env_file=None)

    def test_webhook_secret_exactly_16(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """webhook_secret ровно 16 символов — допустим."""
        env = _valid_env()
        env["WEBHOOK_SECRET"] = "a" * 16
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        settings = Settings(_env_file=None)
        assert len(settings.webhook_secret) == 16


# =========================================================================
# 7. Валидация encryption_key — формат Fernet (base64, 44 символа)
# =========================================================================


class TestEncryptionKeyValidation:
    """[SRE_MARKER] encryption_key должен быть валидным Fernet-ключом (44 символа base64)."""

    def test_encryption_key_too_short(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ключ короче 44 символов → ValidationError."""
        env = _valid_env()
        env["ENCRYPTION_KEY"] = "dG9vc2hvcnQ="  # слишком короткий base64
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(
            ValidationError, match="(?i)encryption|fernet|key|44|base64"
        ):
            Settings(_env_file=None)

    def test_encryption_key_invalid_base64(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ключ с невалидными base64-символами → ValidationError."""
        env = _valid_env()
        env["ENCRYPTION_KEY"] = "!" * 44  # 44 символа, но не base64
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)encryption|fernet|key|base64"):
            Settings(_env_file=None)

    def test_encryption_key_wrong_length(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ключ длиной 28 символов (валидный base64, но не 44) → ValidationError."""
        env = _valid_env()
        env["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(
            b"0" * 20
        ).decode()  # 28 символов
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)encryption|fernet|key|44"):
            Settings(_env_file=None)

    def test_valid_fernet_key_accepted(self, valid_env: dict[str, str]) -> None:
        """Валидный Fernet-ключ (44 символа base64) проходит валидацию."""
        settings = Settings(_env_file=None)
        assert settings.encryption_key == _VALID_FERNET_KEY
        assert len(settings.encryption_key) == 44


# =========================================================================
# 8. Валидация external_http_timeout — диапазон [5, 120]
# =========================================================================


class TestExternalHttpTimeoutValidation:
    """external_http_timeout должен быть в диапазоне [5, 120]."""

    @pytest.mark.parametrize(
        "bad_value",
        ["0", "1", "4", "-1", "-100"],
    )
    def test_timeout_below_minimum(
        self,
        monkeypatch: pytest.MonkeyPatch,
        bad_value: str,
    ) -> None:
        """Значение < 5 → ValidationError."""
        env = _valid_env()
        env["EXTERNAL_HTTP_TIMEOUT"] = bad_value
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)timeout|range|5|120|диапазон"):
            Settings(_env_file=None)

    @pytest.mark.parametrize(
        "bad_value",
        ["121", "200", "999"],
    )
    def test_timeout_above_maximum(
        self,
        monkeypatch: pytest.MonkeyPatch,
        bad_value: str,
    ) -> None:
        """Значение > 120 → ValidationError."""
        env = _valid_env()
        env["EXTERNAL_HTTP_TIMEOUT"] = bad_value
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)timeout|range|5|120|диапазон"):
            Settings(_env_file=None)

    @pytest.mark.parametrize(
        "good_value,expected",
        [("5", 5), ("60", 60), ("120", 120)],
    )
    def test_timeout_within_range(
        self,
        monkeypatch: pytest.MonkeyPatch,
        good_value: str,
        expected: int,
    ) -> None:
        """Значения на границах и внутри диапазона [5, 120] допустимы."""
        env = _valid_env()
        env["EXTERNAL_HTTP_TIMEOUT"] = good_value
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        settings = Settings(_env_file=None)
        assert settings.external_http_timeout == expected

    def test_timeout_is_int_type(self, valid_env: dict[str, str]) -> None:
        """Тип external_http_timeout — int (каст из строки окружения)."""
        settings = Settings(_env_file=None)
        assert isinstance(settings.external_http_timeout, int)


# =========================================================================
# 9. Валидация database_url — непустая строка
# =========================================================================


class TestDatabaseUrlValidation:
    """database_url должен быть непустой строкой."""

    def test_empty_database_url_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty string database_url → ValidationError."""
        env = _valid_env()
        env["DATABASE_URL"] = ""
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        with pytest.raises(ValidationError, match="(?i)database_url|empty|пуст"):
            Settings(_env_file=None)


# =========================================================================
# 10. Синглтон get_settings()
# =========================================================================


class TestGetSettings:
    """get_settings() возвращает кэшированный экземпляр Settings."""

    def test_returns_settings_instance(
        self,
        valid_env: dict[str, str],
        isolated_env: None,
    ) -> None:
        """get_settings() возвращает экземпляр Settings."""
        get_settings.cache_clear()
        result = get_settings()
        assert isinstance(result, Settings)

    def test_singleton_behavior(
        self,
        valid_env: dict[str, str],
        isolated_env: None,
    ) -> None:
        """Повторный вызов get_settings() возвращает тот же объект (кэш)."""
        get_settings.cache_clear()
        first = get_settings()
        second = get_settings()
        assert first is second

    def test_cache_clear_creates_new_instance(
        self,
        valid_env: dict[str, str],
        isolated_env: None,
    ) -> None:
        """После cache_clear() создаётся новый экземпляр."""
        get_settings.cache_clear()
        first = get_settings()
        get_settings.cache_clear()
        second = get_settings()
        assert first is not second


# =========================================================================
# 11. [UPGRADE] Feature flag: enable_tester_console (main_upgrade_spec §2)
# =========================================================================


class TestEnableTesterConsole:
    """Tests for нового поля enable_tester_console.

    main_upgrade_spec.md §2: tester_router подключается условно,
    только если settings.enable_tester_console == True.
    По умолчанию False (production).
    """

    def test_enable_tester_console_default_is_false(
        self, valid_env: dict[str, str]
    ) -> None:
        """enable_tester_console по умолчанию = False (production-safe)."""
        settings = Settings(_env_file=None)
        assert hasattr(settings, "enable_tester_console"), (
            "Settings должен иметь поле enable_tester_console"
        )
        assert settings.enable_tester_console is False

    def test_enable_tester_console_true_from_env(
        self, monkeypatch: pytest.MonkeyPatch, valid_env: dict[str, str]
    ) -> None:
        """enable_tester_console=true из окружения → True."""
        monkeypatch.setenv("ENABLE_TESTER_CONSOLE", "true")
        settings = Settings(_env_file=None)
        assert settings.enable_tester_console is True

    def test_enable_tester_console_false_from_env(
        self, monkeypatch: pytest.MonkeyPatch, valid_env: dict[str, str]
    ) -> None:
        """enable_tester_console=false из окружения → False."""
        monkeypatch.setenv("ENABLE_TESTER_CONSOLE", "false")
        settings = Settings(_env_file=None)
        assert settings.enable_tester_console is False

    def test_enable_tester_console_is_bool_type(
        self, valid_env: dict[str, str]
    ) -> None:
        """Тип enable_tester_console — bool."""
        settings = Settings(_env_file=None)
        assert isinstance(settings.enable_tester_console, bool)

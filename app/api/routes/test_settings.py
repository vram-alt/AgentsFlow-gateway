from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes import settings


@pytest.mark.asyncio
async def test_get_demo_mode_falls_back_to_config_when_env_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(demo_mode=True))

    result = await settings.get_demo_mode()

    assert result == {"enabled": True}


@pytest.mark.asyncio
async def test_set_demo_mode_false_overrides_true_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(demo_mode=True))

    result = await settings.set_demo_mode(settings.DemoModeRequest(enabled=False))

    assert result["enabled"] is False
    assert settings.os.environ["DEMO_MODE"] == "false"


@pytest.mark.asyncio
async def test_set_demo_mode_true_sets_explicit_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(demo_mode=False))

    result = await settings.set_demo_mode(settings.DemoModeRequest(enabled=True))

    assert result["enabled"] is True
    assert settings.os.environ["DEMO_MODE"] == "true"

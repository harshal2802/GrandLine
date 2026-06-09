"""Tests for the production-settings startup guard."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.main import validate_production_settings


class TestValidateProductionSettings:
    def test_allows_default_secret_in_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "debug", True)
        monkeypatch.setattr(settings, "jwt_secret_key", "change-me-in-production")
        validate_production_settings()

    def test_rejects_default_secret_outside_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "debug", False)
        monkeypatch.setattr(settings, "jwt_secret_key", "change-me-in-production")
        with pytest.raises(RuntimeError, match="GRANDLINE_JWT_SECRET_KEY"):
            validate_production_settings()

    def test_allows_custom_secret_outside_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "debug", False)
        monkeypatch.setattr(settings, "jwt_secret_key", "a-real-secret")
        validate_production_settings()

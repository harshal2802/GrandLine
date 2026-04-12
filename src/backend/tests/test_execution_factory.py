"""Tests for execution backend factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCreateBackend:
    def test_creates_gvisor_backend(self) -> None:
        from app.execution.factory import create_backend
        from app.execution.gvisor_backend import GVisorContainerBackend

        settings = MagicMock()
        settings.execution_backend = "gvisor"
        with patch("app.execution.gvisor_backend.aiodocker.Docker"):
            backend = create_backend(settings)

        assert isinstance(backend, GVisorContainerBackend)

    def test_raises_for_unknown_backend(self) -> None:
        from app.execution.factory import create_backend

        settings = MagicMock()
        settings.execution_backend = "unknown"

        with pytest.raises(ValueError, match="Unknown execution backend"):
            create_backend(settings)

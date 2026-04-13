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


class TestCreateGitBackend:
    def test_creates_backend_with_network_enabled(self) -> None:
        from app.execution.factory import create_git_backend
        from app.execution.gvisor_backend import GVisorContainerBackend

        settings = MagicMock()
        settings.execution_backend = "gvisor"
        settings.git_sandbox_image = "bitnami/git:latest"
        settings.execution_gvisor_runtime = "runsc"
        settings.git_sandbox_memory_limit = "512m"
        settings.execution_cpu_quota = 100000
        settings.execution_cpu_period = 100000

        with patch("app.execution.gvisor_backend.aiodocker.Docker"):
            backend = create_git_backend(settings)

        assert isinstance(backend, GVisorContainerBackend)
        assert backend._settings.execution_network_enabled is True
        assert backend._settings.execution_image == "bitnami/git:latest"

    def test_raises_for_unknown_backend(self) -> None:
        from app.execution.factory import create_git_backend

        settings = MagicMock()
        settings.execution_backend = "unknown"

        with pytest.raises(ValueError, match="Unknown execution backend"):
            create_git_backend(settings)

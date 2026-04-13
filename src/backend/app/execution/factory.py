"""Factory for creating execution backends."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.execution.backend import ExecutionBackend


def create_backend(settings: Any) -> ExecutionBackend:
    name = getattr(settings, "execution_backend", "gvisor")
    if name == "gvisor":
        from app.execution.gvisor_backend import GVisorContainerBackend

        return GVisorContainerBackend(settings)
    raise ValueError(f"Unknown execution backend: {name}")


def create_git_backend(settings: Any) -> ExecutionBackend:
    """Create a backend configured for git operations (network enabled, git image)."""
    git_settings = SimpleNamespace(
        execution_image=settings.git_sandbox_image,
        execution_gvisor_runtime=settings.execution_gvisor_runtime,
        execution_memory_limit=settings.git_sandbox_memory_limit,
        execution_cpu_quota=settings.execution_cpu_quota,
        execution_cpu_period=settings.execution_cpu_period,
        execution_network_enabled=True,
    )
    name = getattr(settings, "execution_backend", "gvisor")
    if name == "gvisor":
        from app.execution.gvisor_backend import GVisorContainerBackend

        return GVisorContainerBackend(git_settings)
    raise ValueError(f"Unknown execution backend: {name}")

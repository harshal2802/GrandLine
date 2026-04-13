"""Factory for creating execution backends."""

from __future__ import annotations

from typing import Any

from app.execution.backend import ExecutionBackend


def create_backend(settings: Any) -> ExecutionBackend:
    name = getattr(settings, "execution_backend", "gvisor")
    if name == "gvisor":
        from app.execution.gvisor_backend import GVisorContainerBackend

        return GVisorContainerBackend(settings)
    raise ValueError(f"Unknown execution backend: {name}")

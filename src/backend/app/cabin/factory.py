"""Factory for creating Cabin backends.

Mirrors ``app.execution.factory`` / ``app.browser.factory``: selects the backend on
the ``cabin_backend`` setting (env ``GRANDLINE_CABIN_BACKEND``). The default is
``"null"`` (deterministic, container-free, CI-safe); ``"gvisor"`` opts into the real
persistent-per-user container backend. An unknown value raises ``ValueError``.

The backend imports are LAZY (inside the branches) so that selecting the Null
backend never imports the gVisor module's ``aiodocker``-touching code path.
"""

from __future__ import annotations

from typing import Any

from app.cabin.backend import CabinBackend


def create_cabin_backend(settings: Any) -> CabinBackend:
    name = getattr(settings, "cabin_backend", "null")
    if name == "null":
        from app.cabin.null_backend import NullCabinBackend

        return NullCabinBackend()
    if name == "gvisor":
        from app.cabin.gvisor_backend import GVisorCabinBackend

        return GVisorCabinBackend(settings)
    raise ValueError(f"Unknown cabin backend: {name}")

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

TierLiteral = Literal["preview", "staging", "production"]


@dataclass(frozen=True)
class DeploymentArtifact:
    voyage_id: uuid.UUID
    tier: TierLiteral
    git_ref: str
    git_sha: str | None
    # Reserved for future real backends (Docker/k8s manifest path). v1 callers
    # always pass None; kept on the ABC for forward-compat so real backends can
    # opt into it without changing the service layer signature.
    manifest_path: str | None = None


@dataclass(frozen=True)
class DeploymentResult:
    status: Literal["completed", "failed"]
    url: str | None
    backend_log: str
    error: str | None = None


class DeploymentError(Exception):
    """Raised for backend-internal errors only (e.g. client connection failure).
    A deploy that fails should return DeploymentResult(status='failed', ...)
    rather than raising."""


class DeploymentBackend(ABC):
    @abstractmethod
    async def deploy(self, artifact: DeploymentArtifact) -> DeploymentResult:
        """Deploy the artifact to the given tier."""
        ...

    @abstractmethod
    async def status(
        self,
        voyage_id: uuid.UUID,
        tier: TierLiteral,
    ) -> DeploymentResult | None:
        """Return the last deploy result for (voyage, tier), or None."""
        ...

    async def close(self) -> None:
        """Release resources (e.g. HTTP client session)."""

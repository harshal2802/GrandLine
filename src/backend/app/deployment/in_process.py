from __future__ import annotations

import uuid

from app.deployment.backend import (
    DeploymentArtifact,
    DeploymentBackend,
    DeploymentResult,
    TierLiteral,
)


class InProcessDeploymentBackend(DeploymentBackend):
    """Simulated deployment backend. Records deploys in an in-memory dict and
    returns synthetic URLs. Used for v1 (no real cluster) and tests.

    Fail-injection: if `fail_tiers` contains the tier being deployed,
    `deploy()` returns status='failed' with a synthetic log — useful for
    exercising the diagnose path in tests without patching."""

    def __init__(self, *, fail_tiers: set[str] | None = None) -> None:
        self._records: dict[tuple[uuid.UUID, str], DeploymentResult] = {}
        self._fail_tiers = fail_tiers or set()

    async def deploy(self, artifact: DeploymentArtifact) -> DeploymentResult:
        if artifact.tier in self._fail_tiers:
            result = DeploymentResult(
                status="failed",
                url=None,
                backend_log=(
                    f"simulated failure for tier={artifact.tier} "
                    f"ref={artifact.git_ref} sha={artifact.git_sha}"
                ),
                error="SimulatedFailure",
            )
        else:
            url = f"http://{artifact.tier}.voyage-{artifact.voyage_id.hex[:8]}.local"
            result = DeploymentResult(
                status="completed",
                url=url,
                backend_log=(
                    f"deployed tier={artifact.tier} ref={artifact.git_ref} "
                    f"sha={artifact.git_sha} url={url}"
                ),
                error=None,
            )
        self._records[(artifact.voyage_id, artifact.tier)] = result
        return result

    async def status(
        self,
        voyage_id: uuid.UUID,
        tier: TierLiteral,
    ) -> DeploymentResult | None:
        return self._records.get((voyage_id, tier))

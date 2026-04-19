"""Tests for DeploymentBackend ABC contract and InProcessDeploymentBackend."""

from __future__ import annotations

import uuid

import pytest

from app.deployment.backend import DeploymentArtifact, DeploymentResult
from app.deployment.in_process import InProcessDeploymentBackend


@pytest.fixture
def voyage_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def artifact(voyage_id: uuid.UUID) -> DeploymentArtifact:
    return DeploymentArtifact(
        voyage_id=voyage_id,
        tier="preview",
        git_ref="agent/shipwright/abc",
        git_sha="deadbeef",
    )


class TestInProcessDeployHappyPath:
    async def test_deploy_returns_completed(self, artifact: DeploymentArtifact) -> None:
        backend = InProcessDeploymentBackend()
        result = await backend.deploy(artifact)
        assert result.status == "completed"
        assert result.url is not None
        assert artifact.tier in result.url
        assert artifact.voyage_id.hex[:8] in result.url
        assert result.error is None

    async def test_deploy_log_contains_ref_and_sha(self, artifact: DeploymentArtifact) -> None:
        backend = InProcessDeploymentBackend()
        result = await backend.deploy(artifact)
        assert artifact.git_ref in result.backend_log
        assert artifact.git_sha in result.backend_log  # type: ignore[operator]


class TestInProcessFailInjection:
    async def test_deploy_fails_when_tier_in_fail_tiers(self, artifact: DeploymentArtifact) -> None:
        backend = InProcessDeploymentBackend(fail_tiers={"preview"})
        result = await backend.deploy(artifact)
        assert result.status == "failed"
        assert result.url is None
        assert result.error == "SimulatedFailure"

    async def test_deploy_succeeds_when_tier_not_in_fail_tiers(self, voyage_id: uuid.UUID) -> None:
        backend = InProcessDeploymentBackend(fail_tiers={"production"})
        staging_artifact = DeploymentArtifact(
            voyage_id=voyage_id,
            tier="staging",
            git_ref="staging",
            git_sha="abc",
        )
        result = await backend.deploy(staging_artifact)
        assert result.status == "completed"


class TestInProcessStatusLookup:
    async def test_status_none_before_deploy(self, voyage_id: uuid.UUID) -> None:
        backend = InProcessDeploymentBackend()
        assert await backend.status(voyage_id, "preview") is None

    async def test_status_returns_last_result(self, artifact: DeploymentArtifact) -> None:
        backend = InProcessDeploymentBackend()
        await backend.deploy(artifact)
        status = await backend.status(artifact.voyage_id, artifact.tier)
        assert status is not None
        assert status.status == "completed"

    async def test_status_isolated_per_voyage_and_tier(self, artifact: DeploymentArtifact) -> None:
        backend = InProcessDeploymentBackend()
        await backend.deploy(artifact)
        other_voyage = uuid.uuid4()
        assert await backend.status(other_voyage, artifact.tier) is None
        assert await backend.status(artifact.voyage_id, "production") is None


class TestDeploymentResult:
    def test_frozen_dataclass(self) -> None:
        r = DeploymentResult(status="completed", url="http://x", backend_log="log")
        with pytest.raises((AttributeError, Exception)):
            r.status = "failed"  # type: ignore[misc]

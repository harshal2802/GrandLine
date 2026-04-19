"""Tests for Helmsman Agent Pydantic schemas."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.deployment import (
    DeploymentDiagnosisSpec,
    DeploymentListResponse,
    DeploymentResponse,
    DeployRequest,
    RollbackRequest,
)


class TestDeployRequest:
    def test_accepts_valid_preview(self) -> None:
        req = DeployRequest(tier="preview")
        assert req.tier == "preview"
        assert req.git_ref is None
        assert req.approved_by is None

    def test_accepts_valid_production_with_approval(self) -> None:
        approver = uuid.uuid4()
        req = DeployRequest(tier="production", git_ref="main", approved_by=approver)
        assert req.approved_by == approver

    def test_rejects_unknown_tier(self) -> None:
        with pytest.raises(ValidationError):
            DeployRequest(tier="yolo")  # type: ignore[arg-type]

    def test_accepts_staging_without_approval(self) -> None:
        req = DeployRequest(tier="staging")
        assert req.approved_by is None


class TestRollbackRequest:
    def test_accepts_any_tier(self) -> None:
        req = RollbackRequest(tier="staging")
        assert req.tier == "staging"

    def test_rejects_unknown_tier(self) -> None:
        with pytest.raises(ValidationError):
            RollbackRequest(tier="yolo")  # type: ignore[arg-type]


class TestDeploymentDiagnosisSpec:
    def test_accepts_valid(self) -> None:
        spec = DeploymentDiagnosisSpec(
            summary="Build failed",
            likely_cause="Missing env var",
            suggested_action="Set APP_URL",
        )
        assert spec.summary == "Build failed"

    def test_rejects_empty_summary(self) -> None:
        with pytest.raises(ValidationError):
            DeploymentDiagnosisSpec(
                summary="",
                likely_cause="x",
                suggested_action="y",
            )


class TestDeploymentResponse:
    def test_accepts_valid(self) -> None:
        resp = DeploymentResponse(
            voyage_id=uuid.uuid4(),
            deployment_id=uuid.uuid4(),
            tier="preview",
            action="deploy",
            status="completed",
            git_ref="main",
            git_sha="abc123",
            url="http://x.local",
            diagnosis=None,
        )
        assert resp.status == "completed"

    def test_rejects_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            DeploymentResponse(
                voyage_id=uuid.uuid4(),
                deployment_id=uuid.uuid4(),
                tier="preview",
                action="deploy",
                status="weird",  # type: ignore[arg-type]
                git_ref="main",
                git_sha=None,
                url=None,
                diagnosis=None,
            )


class TestDeploymentListResponse:
    def test_accepts_empty_list(self) -> None:
        resp = DeploymentListResponse(
            voyage_id=uuid.uuid4(),
            tier=None,
            deployments=[],
        )
        assert resp.deployments == []

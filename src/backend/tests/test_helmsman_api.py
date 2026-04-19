"""Tests for Helmsman Agent REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus
from app.schemas.deployment import DeploymentResponse, DeployRequest, RollbackRequest
from app.services.helmsman_service import HelmsmanError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
APPROVER_ID = uuid.uuid4()
DEPLOY_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(status: str = VoyageStatus.CHARTED.value) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    voyage.target_repo = None
    return voyage


def _mock_deployment(
    tier: str = "preview",
    action: str = "deploy",
    status_: str = "completed",
) -> MagicMock:
    d = MagicMock()
    d.id = uuid.uuid4()
    d.voyage_id = VOYAGE_ID
    d.tier = tier
    d.action = action
    d.git_ref = "main"
    d.git_sha = "abc"
    d.status = status_
    d.approved_by = None
    d.url = "http://x.local" if status_ == "completed" else None
    d.backend_log = "log"
    d.diagnosis = None
    d.previous_deployment_id = None
    d.created_at = datetime(2026, 4, 17, tzinfo=UTC)
    d.updated_at = datetime(2026, 4, 17, tzinfo=UTC)
    return d


def _success_response() -> DeploymentResponse:
    return DeploymentResponse(
        voyage_id=VOYAGE_ID,
        deployment_id=DEPLOY_ID,
        tier="preview",
        action="deploy",
        status="completed",
        git_ref="main",
        git_sha="abc",
        url="http://preview.voyage.local",
        diagnosis=None,
    )


def _mock_helmsman_service() -> AsyncMock:
    svc = AsyncMock()
    svc.deploy = AsyncMock(return_value=_success_response())
    svc.rollback = AsyncMock(
        return_value=DeploymentResponse(
            voyage_id=VOYAGE_ID,
            deployment_id=DEPLOY_ID,
            tier="preview",
            action="rollback",
            status="completed",
            git_ref="main",
            git_sha="abc",
            url="http://preview.voyage.local",
            diagnosis=None,
        )
    )
    return svc


def _mock_helmsman_reader() -> AsyncMock:
    svc = AsyncMock()
    svc.get_deployments = AsyncMock(return_value=[])
    return svc


class TestDeployEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_with_deployment(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        body = DeployRequest(tier="preview")

        result = await deploy_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.status == "completed"
        assert result.action == "deploy"
        svc.deploy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_403_on_approval_required(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        svc.deploy.side_effect = HelmsmanError(
            "APPROVAL_REQUIRED", "Production deploys require approved_by"
        )
        body = DeployRequest(tier="production")

        with pytest.raises(HTTPException) as exc_info:
            await deploy_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"]["code"] == "APPROVAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_not_charted(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        svc.deploy.side_effect = HelmsmanError(
            "VOYAGE_NOT_DEPLOYABLE", "Voyage status is DEPLOYING"
        )
        body = DeployRequest(tier="preview")

        with pytest.raises(HTTPException) as exc_info:
            await deploy_voyage(
                VOYAGE_ID,
                body,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.DEPLOYING.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_DEPLOYABLE"

    @pytest.mark.asyncio
    async def test_approval_takes_precedence_over_status(self) -> None:
        """Production deploy to a non-CHARTED voyage without approval should return
        403 (APPROVAL_REQUIRED), not 409 (VOYAGE_NOT_DEPLOYABLE) — service enforces
        ordering."""
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        svc.deploy.side_effect = HelmsmanError(
            "APPROVAL_REQUIRED", "Production deploys require approved_by"
        )
        body = DeployRequest(tier="production")

        with pytest.raises(HTTPException) as exc_info:
            await deploy_voyage(
                VOYAGE_ID,
                body,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.DEPLOYING.value),
                svc,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_422_on_deployment_failed(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        svc.deploy.side_effect = HelmsmanError("DEPLOYMENT_FAILED", "Build error")
        body = DeployRequest(tier="preview")

        with pytest.raises(HTTPException) as exc_info:
            await deploy_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "DEPLOYMENT_FAILED"

    @pytest.mark.asyncio
    async def test_returns_422_on_git_ref_unresolvable(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        svc.deploy.side_effect = HelmsmanError("GIT_REF_UNRESOLVABLE", "Could not resolve git_ref")
        body = DeployRequest(tier="preview", git_ref="nonexistent")

        with pytest.raises(HTTPException) as exc_info:
            await deploy_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "GIT_REF_UNRESOLVABLE"

    @pytest.mark.asyncio
    async def test_passes_approved_by_to_service(self) -> None:
        from app.api.v1.helmsman import deploy_voyage

        svc = _mock_helmsman_service()
        body = DeployRequest(tier="production", approved_by=APPROVER_ID)

        await deploy_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert svc.deploy.call_args.kwargs["approved_by"] == APPROVER_ID


class TestRollbackEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_on_success(self) -> None:
        from app.api.v1.helmsman import rollback_voyage

        svc = _mock_helmsman_service()
        body = RollbackRequest(tier="preview")

        result = await rollback_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.action == "rollback"
        svc.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_404_no_previous_deployment(self) -> None:
        from app.api.v1.helmsman import rollback_voyage

        svc = _mock_helmsman_service()
        svc.rollback.side_effect = HelmsmanError(
            "NO_PREVIOUS_DEPLOYMENT", "No completed deploy found"
        )
        body = RollbackRequest(tier="preview")

        with pytest.raises(HTTPException) as exc_info:
            await rollback_voyage(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error"]["code"] == "NO_PREVIOUS_DEPLOYMENT"

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_not_charted(self) -> None:
        from app.api.v1.helmsman import rollback_voyage

        svc = _mock_helmsman_service()
        svc.rollback.side_effect = HelmsmanError(
            "VOYAGE_NOT_DEPLOYABLE", "Voyage status is BUILDING"
        )
        body = RollbackRequest(tier="preview")

        with pytest.raises(HTTPException) as exc_info:
            await rollback_voyage(
                VOYAGE_ID,
                body,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.BUILDING.value),
                svc,
            )

        assert exc_info.value.status_code == 409


class TestListDeploymentsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        from app.api.v1.helmsman import list_deployments

        reader = _mock_helmsman_reader()
        reader.get_deployments.return_value = [_mock_deployment()]

        result = await list_deployments(VOYAGE_ID, None, _mock_user(), _mock_voyage(), reader)

        assert len(result.deployments) == 1
        assert result.tier is None

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        from app.api.v1.helmsman import list_deployments

        reader = _mock_helmsman_reader()

        result = await list_deployments(VOYAGE_ID, None, _mock_user(), _mock_voyage(), reader)

        assert result.deployments == []

    @pytest.mark.asyncio
    async def test_filters_by_tier(self) -> None:
        from app.api.v1.helmsman import list_deployments

        reader = _mock_helmsman_reader()

        result = await list_deployments(VOYAGE_ID, "preview", _mock_user(), _mock_voyage(), reader)

        reader.get_deployments.assert_awaited_once_with(VOYAGE_ID, "preview")
        assert result.tier == "preview"

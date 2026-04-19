"""Tests for HelmsmanService (mocked dependencies)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.den_den_mushi.events import (
    DeploymentCompletedEvent,
    DeploymentFailedEvent,
    DeploymentStartedEvent,
)
from app.models.deployment import Deployment
from app.models.enums import VoyageStatus
from app.models.vivre_card import VivreCard
from app.services.git_service import GitError
from app.services.helmsman_service import (
    HelmsmanError,
    HelmsmanService,
    _require_production_approval,
)

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
APPROVER_ID = uuid.uuid4()


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    target_repo: str | None = "git@github.com:user/repo.git",
) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    voyage.target_repo = target_repo
    return voyage


def _graph_state(
    *,
    status: str = "completed",
    url: str | None = "http://preview.voyage-abc.local",
    backend_log: str = "ok",
    error: str | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "voyage_id": VOYAGE_ID,
        "user_id": USER_ID,
        "tier": "preview",
        "git_ref": "agent/shipwright/abc",
        "git_sha": "deadbeef",
        "status": status,
        "url": url,
        "backend_log": backend_log,
        "error": error,
        "diagnosis": diagnosis,
    }


@pytest.fixture
def mock_dial_router() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_mushi() -> AsyncMock:
    m = AsyncMock()
    m.publish = AsyncMock(return_value="msg-1")
    return m


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    result_mock.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def mock_backend() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_git() -> AsyncMock:
    g = AsyncMock()
    g.get_head_sha = AsyncMock(return_value="deadbeef")
    return g


@pytest.fixture
def service(
    mock_dial_router: AsyncMock,
    mock_mushi: AsyncMock,
    mock_session: AsyncMock,
    mock_backend: AsyncMock,
    mock_git: AsyncMock,
) -> HelmsmanService:
    svc = HelmsmanService(
        mock_dial_router,
        mock_mushi,
        mock_session,
        deployment_backend=mock_backend,
        git_service=mock_git,
    )
    svc._graph = AsyncMock()  # type: ignore[assignment]
    svc._graph.ainvoke = AsyncMock(return_value=_graph_state())  # type: ignore[attr-defined]
    return svc


class TestApprovalGate:
    def test_production_without_approval_raises(self) -> None:
        with pytest.raises(HelmsmanError) as exc:
            _require_production_approval("production", None)
        assert exc.value.code == "APPROVAL_REQUIRED"

    def test_production_with_approval_passes(self) -> None:
        _require_production_approval("production", APPROVER_ID)

    def test_preview_without_approval_passes(self) -> None:
        _require_production_approval("preview", None)

    def test_staging_without_approval_passes(self) -> None:
        _require_production_approval("staging", None)


class TestDeployHappyPath:
    @pytest.mark.asyncio
    async def test_returns_completed_response(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage()
        resp = await service.deploy(voyage, "preview", USER_ID)
        assert resp.status == "completed"
        assert resp.url == "http://preview.voyage-abc.local"
        assert resp.action == "deploy"
        assert resp.diagnosis is None

    @pytest.mark.asyncio
    async def test_sets_status_to_deploying_during_call(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        observed: list[str] = []

        async def record() -> None:
            observed.append(voyage.status)

        mock_session.flush.side_effect = record
        await service.deploy(voyage, "preview", USER_ID)
        assert VoyageStatus.DEPLOYING.value in observed

    @pytest.mark.asyncio
    async def test_restores_charted_after_success(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_persists_deployment_and_vivre_card(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)

        added = [c.args[0] for c in mock_session.add.call_args_list]
        assert any(isinstance(x, Deployment) for x in added)
        assert any(isinstance(x, VivreCard) for x in added)

    @pytest.mark.asyncio
    async def test_commits_atomically(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_uses_default_git_ref_for_preview(
        self, service: HelmsmanService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)
        mock_git.get_head_sha.assert_awaited_once()
        ref = mock_git.get_head_sha.call_args.args[2]
        assert "agent/shipwright/" in ref

    @pytest.mark.asyncio
    async def test_uses_provided_git_ref(
        self, service: HelmsmanService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID, git_ref="custom-branch")
        ref = mock_git.get_head_sha.call_args.args[2]
        assert ref == "custom-branch"

    @pytest.mark.asyncio
    async def test_uses_default_git_ref_for_staging(
        self, service: HelmsmanService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "staging", USER_ID)
        assert mock_git.get_head_sha.call_args.args[2] == "staging"

    @pytest.mark.asyncio
    async def test_uses_default_git_ref_for_production(
        self, service: HelmsmanService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "production", USER_ID, approved_by=APPROVER_ID)
        assert mock_git.get_head_sha.call_args.args[2] == "main"


class TestApprovalEnforcement:
    @pytest.mark.asyncio
    async def test_production_without_approval_raises(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError) as exc:
            await service.deploy(voyage, "production", USER_ID)
        assert exc.value.code == "APPROVAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_production_with_approval_succeeds(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage()
        resp = await service.deploy(voyage, "production", USER_ID, approved_by=APPROVER_ID)
        assert resp.status == "completed"

    @pytest.mark.asyncio
    async def test_approval_checked_before_status_gate(self, service: HelmsmanService) -> None:
        # voyage NOT in CHARTED — but since no approval is provided, approval
        # error should fire first (403 vs 409 precedence)
        voyage = _mock_voyage(status=VoyageStatus.DEPLOYING.value)
        with pytest.raises(HelmsmanError) as exc:
            await service.deploy(voyage, "production", USER_ID)
        assert exc.value.code == "APPROVAL_REQUIRED"


class TestStatusGate:
    @pytest.mark.asyncio
    async def test_non_charted_voyage_raises(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage(status=VoyageStatus.DEPLOYING.value)
        with pytest.raises(HelmsmanError) as exc:
            await service.deploy(voyage, "preview", USER_ID)
        assert exc.value.code == "VOYAGE_NOT_DEPLOYABLE"

    @pytest.mark.asyncio
    async def test_rollback_non_charted_voyage_raises(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)
        with pytest.raises(HelmsmanError) as exc:
            await service.rollback(voyage, "preview", USER_ID)
        assert exc.value.code == "VOYAGE_NOT_DEPLOYABLE"


class TestDeployFailurePath:
    @pytest.mark.asyncio
    async def test_failed_graph_raises_deployment_failed(self, service: HelmsmanService) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(
                status="failed",
                url=None,
                diagnosis={
                    "summary": "Build error",
                    "likely_cause": "x",
                    "suggested_action": "y",
                },
            )
        )
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError) as exc:
            await service.deploy(voyage, "preview", USER_ID)
        assert exc.value.code == "DEPLOYMENT_FAILED"
        assert "Build error" in exc.value.message

    @pytest.mark.asyncio
    async def test_failed_deploy_still_commits_row(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(status="failed", url=None)
        )
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError):
            await service.deploy(voyage, "preview", USER_ID)
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_failed_deploy_restores_charted(self, service: HelmsmanService) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(status="failed", url=None)
        )
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError):
            await service.deploy(voyage, "preview", USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_graph_exception_restores_charted(self, service: HelmsmanService) -> None:
        service._graph.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]
        voyage = _mock_voyage()
        with pytest.raises(RuntimeError):
            await service.deploy(voyage, "preview", USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value


class TestGitRefResolution:
    @pytest.mark.asyncio
    async def test_git_error_raises_git_ref_unresolvable(
        self, service: HelmsmanService, mock_git: AsyncMock
    ) -> None:
        mock_git.get_head_sha = AsyncMock(side_effect=GitError("bad ref"))
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError) as exc:
            await service.deploy(voyage, "preview", USER_ID)
        assert exc.value.code == "GIT_REF_UNRESOLVABLE"

    @pytest.mark.asyncio
    async def test_null_target_repo_skips_git_resolution(
        self,
        mock_dial_router: AsyncMock,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
        mock_backend: AsyncMock,
        mock_git: AsyncMock,
    ) -> None:
        svc = HelmsmanService(
            mock_dial_router,
            mock_mushi,
            mock_session,
            deployment_backend=mock_backend,
            git_service=mock_git,
        )
        svc._graph = AsyncMock()  # type: ignore[assignment]
        svc._graph.ainvoke = AsyncMock(return_value=_graph_state())  # type: ignore[attr-defined]
        voyage = _mock_voyage(target_repo=None)
        await svc.deploy(voyage, "preview", USER_ID)
        mock_git.get_head_sha.assert_not_awaited()


class TestRollback:
    @pytest.mark.asyncio
    async def test_no_previous_deploy_raises(self, service: HelmsmanService) -> None:
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError) as exc:
            await service.rollback(voyage, "preview", USER_ID)
        assert exc.value.code == "NO_PREVIOUS_DEPLOYMENT"

    @pytest.mark.asyncio
    async def test_finds_previous_and_redeploys_sha(
        self, service: HelmsmanService, mock_session: AsyncMock, mock_git: AsyncMock
    ) -> None:
        previous = Deployment(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            tier="preview",
            action="deploy",
            git_ref="agent/shipwright/old",
            git_sha="oldsha",
            status="completed",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        voyage = _mock_voyage()
        resp = await service.rollback(voyage, "preview", USER_ID)

        assert resp.action == "rollback"
        assert resp.git_ref == "agent/shipwright/old"
        # rollback does NOT re-resolve the sha via git — uses the previous sha
        mock_git.get_head_sha.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rollback_sets_previous_deployment_id(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        prev_id = uuid.uuid4()
        previous = Deployment(
            id=prev_id,
            voyage_id=VOYAGE_ID,
            tier="preview",
            action="deploy",
            git_ref="ref",
            git_sha="sha",
            status="completed",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        voyage = _mock_voyage()
        await service.rollback(voyage, "preview", USER_ID)

        deployments = [
            c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], Deployment)
        ]
        assert any(d.previous_deployment_id == prev_id for d in deployments)


class TestEventPublishing:
    @pytest.mark.asyncio
    async def test_publishes_started_and_completed_on_success(
        self, service: HelmsmanService, mock_mushi: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)

        published = [c.args[1] for c in mock_mushi.publish.call_args_list]
        assert any(isinstance(e, DeploymentStartedEvent) for e in published)
        assert any(isinstance(e, DeploymentCompletedEvent) for e in published)
        assert not any(isinstance(e, DeploymentFailedEvent) for e in published)

    @pytest.mark.asyncio
    async def test_publishes_started_and_failed_on_failure(
        self, service: HelmsmanService, mock_mushi: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(status="failed", url=None)
        )
        voyage = _mock_voyage()
        with pytest.raises(HelmsmanError):
            await service.deploy(voyage, "preview", USER_ID)

        published = [c.args[1] for c in mock_mushi.publish.call_args_list]
        assert any(isinstance(e, DeploymentStartedEvent) for e in published)
        assert any(isinstance(e, DeploymentFailedEvent) for e in published)
        assert not any(isinstance(e, DeploymentCompletedEvent) for e in published)

    @pytest.mark.asyncio
    async def test_publish_failure_does_not_raise(
        self, service: HelmsmanService, mock_mushi: AsyncMock
    ) -> None:
        mock_mushi.publish = AsyncMock(side_effect=RuntimeError("redis down"))
        voyage = _mock_voyage()
        # Should still return successfully — best-effort events
        resp = await service.deploy(voyage, "preview", USER_ID)
        assert resp.status == "completed"


class TestReaderFactory:
    def test_reader_creates_read_only_instance(self, mock_session: AsyncMock) -> None:
        reader = HelmsmanService.reader(mock_session)
        assert reader._session is mock_session

    @pytest.mark.asyncio
    async def test_reader_get_deployments_works(self, mock_session: AsyncMock) -> None:
        reader = HelmsmanService.reader(mock_session)
        rows = await reader.get_deployments(VOYAGE_ID)
        assert rows == []

    @pytest.mark.asyncio
    async def test_get_deployments_filters_by_tier(self, mock_session: AsyncMock) -> None:
        reader = HelmsmanService.reader(mock_session)
        await reader.get_deployments(VOYAGE_ID, tier="preview")
        mock_session.execute.assert_awaited()


class TestBackendLogTruncation:
    @pytest.mark.asyncio
    async def test_long_log_truncated_to_4000(
        self, service: HelmsmanService, mock_session: AsyncMock
    ) -> None:
        long_log = "X" * 10000
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(backend_log=long_log)
        )
        voyage = _mock_voyage()
        await service.deploy(voyage, "preview", USER_ID)

        deployments = [
            c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], Deployment)
        ]
        assert len(deployments) == 1
        assert len(deployments[0].backend_log) == 4000  # type: ignore[arg-type]

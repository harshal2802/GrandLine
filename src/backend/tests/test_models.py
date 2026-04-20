"""Tests for SQLAlchemy model definitions."""

from sqlalchemy import inspect

from app.models import Base
from app.models.build_artifact import BuildArtifact
from app.models.crew_action import CrewAction
from app.models.deployment import Deployment
from app.models.dial_config import DialConfig
from app.models.enums import CheckpointReason, CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.shipwright_run import ShipwrightRun
from app.models.user import User
from app.models.validation_run import ValidationRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan


def test_all_models_registered_in_metadata() -> None:
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "users",
        "voyages",
        "voyage_plans",
        "poneglyphs",
        "vivre_cards",
        "crew_actions",
        "dial_configs",
        "health_checks",
        "validation_runs",
        "shipwright_runs",
        "build_artifacts",
        "deployments",
    }
    assert expected == table_names


def test_user_table_columns() -> None:
    mapper = inspect(User)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "email",
        "username",
        "hashed_password",
        "is_active",
        "created_at",
        "updated_at",
    }


def test_voyage_table_columns() -> None:
    mapper = inspect(Voyage)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "user_id",
        "title",
        "description",
        "status",
        "target_repo",
        "phase_status",
        "created_at",
        "updated_at",
    }


def test_voyage_phase_status_column_is_jsonb_not_nullable() -> None:
    table = Voyage.__table__
    col = table.c.phase_status
    assert col.nullable is False
    assert col.type.__class__.__name__ == "JSONB"


def test_voyage_plan_table_columns() -> None:
    mapper = inspect(VoyagePlan)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "phases",
        "created_by",
        "version",
        "created_at",
    }


def test_poneglyph_table_columns() -> None:
    mapper = inspect(Poneglyph)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "phase_number",
        "content",
        "metadata",
        "created_by",
        "created_at",
    }


def test_vivre_card_table_columns() -> None:
    mapper = inspect(VivreCard)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "crew_member",
        "state_data",
        "checkpoint_reason",
        "created_at",
    }


def test_crew_action_table_columns() -> None:
    mapper = inspect(CrewAction)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "crew_member",
        "action_type",
        "summary",
        "details",
        "created_at",
    }


def test_dial_config_table_columns() -> None:
    mapper = inspect(DialConfig)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "role_mapping",
        "fallback_chain",
        "created_at",
        "updated_at",
    }


def test_voyage_status_enum_values() -> None:
    assert VoyageStatus.CHARTED.value == "CHARTED"
    assert VoyageStatus.PLANNING.value == "PLANNING"
    assert VoyageStatus.PDD.value == "PDD"
    assert VoyageStatus.TDD.value == "TDD"
    assert VoyageStatus.BUILDING.value == "BUILDING"
    assert VoyageStatus.REVIEWING.value == "REVIEWING"
    assert VoyageStatus.DEPLOYING.value == "DEPLOYING"
    assert VoyageStatus.COMPLETED.value == "COMPLETED"
    assert VoyageStatus.FAILED.value == "FAILED"
    assert VoyageStatus.PAUSED.value == "PAUSED"
    assert VoyageStatus.CANCELLED.value == "CANCELLED"
    assert len(VoyageStatus) == 11


def test_crew_role_enum_values() -> None:
    assert CrewRole.CAPTAIN.value == "captain"
    assert CrewRole.NAVIGATOR.value == "navigator"
    assert CrewRole.DOCTOR.value == "doctor"
    assert CrewRole.SHIPWRIGHT.value == "shipwright"
    assert CrewRole.HELMSMAN.value == "helmsman"
    assert len(CrewRole) == 5


def test_checkpoint_reason_enum_values() -> None:
    assert CheckpointReason.INTERVAL.value == "interval"
    assert CheckpointReason.FAILOVER.value == "failover"
    assert CheckpointReason.PAUSE.value == "pause"
    assert CheckpointReason.MIGRATION.value == "migration"
    assert len(CheckpointReason) == 4


def test_user_relationships() -> None:
    mapper = inspect(User)
    rel_names = {r.key for r in mapper.relationships}
    assert "voyages" in rel_names


def test_voyage_relationships() -> None:
    mapper = inspect(Voyage)
    rel_names = {r.key for r in mapper.relationships}
    expected = {"user", "plans", "poneglyphs", "vivre_cards", "crew_actions", "dial_config"}
    assert expected == rel_names


def test_dial_config_voyage_unique_constraint() -> None:
    table = DialConfig.__table__
    voyage_col = table.c.voyage_id
    assert voyage_col.unique is True


def test_crew_action_crew_member_indexed() -> None:
    table = CrewAction.__table__
    crew_col = table.c.crew_member
    assert crew_col.index is True


def test_health_check_table_columns() -> None:
    mapper = inspect(HealthCheck)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "poneglyph_id",
        "phase_number",
        "file_path",
        "content",
        "framework",
        "last_run_status",
        "last_run_at",
        "last_validation_run_id",
        "created_by",
        "created_at",
    }


def test_validation_run_table_columns() -> None:
    mapper = inspect(ValidationRun)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "status",
        "exit_code",
        "passed_count",
        "failed_count",
        "total_count",
        "output",
        "created_at",
    }


def test_shipwright_run_table_columns() -> None:
    mapper = inspect(ShipwrightRun)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "poneglyph_id",
        "phase_number",
        "status",
        "iteration_count",
        "exit_code",
        "passed_count",
        "failed_count",
        "total_count",
        "output",
        "created_at",
    }


def test_build_artifact_table_columns() -> None:
    mapper = inspect(BuildArtifact)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "shipwright_run_id",
        "phase_number",
        "file_path",
        "content",
        "language",
        "created_by",
        "created_at",
    }


def test_shipwright_run_voyage_phase_indexed() -> None:
    table = ShipwrightRun.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "ix_shipwright_runs_voyage_phase" in index_names


def test_build_artifact_voyage_phase_indexed() -> None:
    table = BuildArtifact.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "ix_build_artifacts_voyage_phase" in index_names


def test_deployment_table_columns() -> None:
    mapper = inspect(Deployment)
    column_names = {c.key for c in mapper.columns}
    assert column_names == {
        "id",
        "voyage_id",
        "tier",
        "action",
        "git_ref",
        "git_sha",
        "status",
        "approved_by",
        "url",
        "backend_log",
        "diagnosis",
        "previous_deployment_id",
        "created_at",
        "updated_at",
    }


def test_deployment_composite_index() -> None:
    table = Deployment.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "ix_deployments_voyage_tier_created" in index_names

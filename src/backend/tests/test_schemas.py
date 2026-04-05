"""Tests for Pydantic schema validation and serialization."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.crew_action import CrewActionRead
from app.schemas.dial_config import DialConfigCreate, DialConfigRead, DialConfigUpdate
from app.schemas.poneglyph import PoneglyphRead
from app.schemas.user import UserCreate, UserRead
from app.schemas.vivre_card import VivreCardCreate, VivreCardRead
from app.schemas.voyage import VoyageCreate, VoyagePlanRead, VoyageRead

NOW = datetime.now(tz=UTC)
VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


# --- UserCreate ---


def test_user_create_valid() -> None:
    schema = UserCreate(email="luffy@grandline.io", username="luffy", password="gomu123")
    assert schema.email == "luffy@grandline.io"
    assert schema.username == "luffy"
    assert schema.password == "gomu123"


def test_user_create_missing_field() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="luffy@grandline.io", username="luffy")  # type: ignore[call-arg]


# --- UserRead ---


def test_user_read_valid() -> None:
    schema = UserRead(
        id=USER_ID,
        email="luffy@grandline.io",
        username="luffy",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    assert schema.id == USER_ID
    assert schema.is_active is True


# --- VoyageCreate ---


def test_voyage_create_minimal() -> None:
    schema = VoyageCreate(title="Find One Piece")
    assert schema.title == "Find One Piece"
    assert schema.description is None
    assert schema.target_repo is None


def test_voyage_create_full() -> None:
    schema = VoyageCreate(
        title="Find One Piece",
        description="Navigate the Grand Line",
        target_repo="harshal2802/treasure",
    )
    assert schema.target_repo == "harshal2802/treasure"


# --- VoyageRead ---


def test_voyage_read_valid() -> None:
    schema = VoyageRead(
        id=VOYAGE_ID,
        user_id=USER_ID,
        title="Voyage 1",
        description=None,
        status="CHARTED",
        target_repo=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert schema.status == "CHARTED"


# --- VoyagePlanRead ---


def test_voyage_plan_read_valid() -> None:
    schema = VoyagePlanRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        phases={"phase_1": {"name": "Foundation", "tasks": []}},
        created_by="captain",
        version=1,
        created_at=NOW,
    )
    assert schema.version == 1
    assert "phase_1" in schema.phases


# --- PoneglyphRead ---


def test_poneglyph_read_valid() -> None:
    schema = PoneglyphRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        phase_number=1,
        content="Build the foundation",
        metadata_={"tags": ["setup"]},
        created_by="navigator",
        created_at=NOW,
    )
    assert schema.phase_number == 1
    assert schema.metadata_ == {"tags": ["setup"]}


def test_poneglyph_read_null_metadata() -> None:
    schema = PoneglyphRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        phase_number=2,
        content="Content here",
        metadata_=None,
        created_by="navigator",
        created_at=NOW,
    )
    assert schema.metadata_ is None


# --- VivreCardCreate ---


def test_vivre_card_create_valid() -> None:
    schema = VivreCardCreate(
        voyage_id=VOYAGE_ID,
        crew_member="captain",
        state_data={"step": 3, "context": {"prompt": "Build auth"}},
        checkpoint_reason="interval",
    )
    assert schema.crew_member == "captain"
    assert schema.checkpoint_reason == "interval"


def test_vivre_card_create_invalid_role() -> None:
    with pytest.raises(ValidationError):
        VivreCardCreate(
            voyage_id=VOYAGE_ID,
            crew_member="pirate",
            state_data={},
            checkpoint_reason="interval",
        )


def test_vivre_card_create_invalid_reason() -> None:
    with pytest.raises(ValidationError):
        VivreCardCreate(
            voyage_id=VOYAGE_ID,
            crew_member="captain",
            state_data={},
            checkpoint_reason="random",
        )


# --- VivreCardRead ---


def test_vivre_card_read_valid() -> None:
    schema = VivreCardRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        crew_member="doctor",
        state_data={"tests_passed": 42},
        checkpoint_reason="pause",
        created_at=NOW,
    )
    assert schema.crew_member == "doctor"


# --- CrewActionRead ---


def test_crew_action_read_valid() -> None:
    schema = CrewActionRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        crew_member="shipwright",
        action_type="code_generation",
        summary="Generated auth module",
        details={"files": ["auth.py", "auth_test.py"]},
        created_at=NOW,
    )
    assert schema.action_type == "code_generation"
    assert schema.details is not None


def test_crew_action_read_null_details() -> None:
    schema = CrewActionRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        crew_member="helmsman",
        action_type="deploy",
        summary="Deployed to staging",
        details=None,
        created_at=NOW,
    )
    assert schema.details is None


# --- DialConfigCreate ---


def test_dial_config_create_valid() -> None:
    schema = DialConfigCreate(
        voyage_id=VOYAGE_ID,
        role_mapping={
            "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            "navigator": {"provider": "openai", "model": "gpt-4o"},
        },
    )
    assert "captain" in schema.role_mapping
    assert schema.fallback_chain is None


def test_dial_config_create_with_fallback() -> None:
    schema = DialConfigCreate(
        voyage_id=VOYAGE_ID,
        role_mapping={"captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}},
        fallback_chain={"order": ["anthropic", "openai"]},
    )
    assert schema.fallback_chain is not None


# --- DialConfigUpdate ---


def test_dial_config_update_partial() -> None:
    schema = DialConfigUpdate(role_mapping={"captain": {"provider": "openai", "model": "gpt-4o"}})
    assert schema.role_mapping is not None
    assert schema.fallback_chain is None


def test_dial_config_update_empty() -> None:
    schema = DialConfigUpdate()
    assert schema.role_mapping is None
    assert schema.fallback_chain is None


# --- DialConfigRead ---


def test_dial_config_read_valid() -> None:
    schema = DialConfigRead(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        role_mapping={"captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}},
        fallback_chain=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert schema.fallback_chain is None

"""Seed script to populate the database with sample data for development."""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import async_session, engine
from app.models.crew_action import CrewAction
from app.models.dial_config import DialConfig
from app.models.poneglyph import Poneglyph
from app.models.user import User
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan


async def seed() -> None:
    async with async_session() as session:
        session: AsyncSession

        # Check if data already exists
        result = await session.execute(text("SELECT count(*) FROM users"))
        if result.scalar_one() > 0:
            print("Database already seeded. Skipping.")
            return

        # Create a sample user
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="luffy@grandline.io",
            username="luffy",
            hashed_password="$2b$12$placeholder_hash_for_seed_data",
        )
        session.add(user)

        # Create a sample voyage
        voyage_id = uuid.uuid4()
        voyage = Voyage(
            id=voyage_id,
            user_id=user_id,
            title="Build the Thousand Sunny",
            description="A full-stack application built with the Straw Hat crew",
            status="CHARTED",
            target_repo="harshal2802/thousand-sunny",
        )
        session.add(voyage)

        # Create a voyage plan
        plan = VoyagePlan(
            id=uuid.uuid4(),
            voyage_id=voyage_id,
            phases={
                "phase_1": {"name": "Foundation", "description": "Project scaffolding and CI/CD"},
                "phase_2": {"name": "Database", "description": "Models, schemas, and migrations"},
                "phase_3": {"name": "Auth", "description": "Authentication and authorization"},
            },
            created_by="captain",
            version=1,
        )
        session.add(plan)

        # Create a poneglyph (PDD artifact)
        poneglyph = Poneglyph(
            id=uuid.uuid4(),
            voyage_id=voyage_id,
            phase_number=1,
            content="Build the project foundation with FastAPI backend and Next.js frontend.",
            metadata_={"tags": ["foundation", "scaffold"], "priority": "high"},
            created_by="navigator",
        )
        session.add(poneglyph)

        # Create a vivre card (state checkpoint)
        vivre_card = VivreCard(
            id=uuid.uuid4(),
            voyage_id=voyage_id,
            crew_member="captain",
            state_data={
                "current_phase": 1,
                "progress": 0.5,
                "context": {"last_action": "Created project scaffold"},
            },
            checkpoint_reason="interval",
        )
        session.add(vivre_card)

        # Create crew actions
        actions = [
            CrewAction(
                id=uuid.uuid4(),
                voyage_id=voyage_id,
                crew_member="captain",
                action_type="plan_creation",
                summary="Created the voyage plan with 3 phases",
                details={"phases_count": 3},
            ),
            CrewAction(
                id=uuid.uuid4(),
                voyage_id=voyage_id,
                crew_member="navigator",
                action_type="pdd_prompt",
                summary="Generated PDD prompt for Phase 1: Foundation",
                details={"phase": 1, "prompt_file": "foundation.md"},
            ),
            CrewAction(
                id=uuid.uuid4(),
                voyage_id=voyage_id,
                crew_member="shipwright",
                action_type="code_generation",
                summary="Implemented project scaffold based on PDD prompt",
                details={"files_created": 12, "lines_of_code": 450},
            ),
        ]
        session.add_all(actions)

        # Create dial config (LLM gateway configuration)
        dial_config = DialConfig(
            id=uuid.uuid4(),
            voyage_id=voyage_id,
            role_mapping={
                "captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                "navigator": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                "shipwright": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                "doctor": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
                "helmsman": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            },
            fallback_chain={
                "order": ["anthropic", "openai"],
                "openai": {"model": "gpt-4o"},
            },
        )
        session.add(dial_config)

        await session.commit()
        print("Seeded database successfully!")
        print(f"  User: {user.username} ({user.email})")
        print(f"  Voyage: {voyage.title}")
        print(f"  Plan: {plan.version} ({len(plan.phases)} phases)")
        print("  Poneglyphs: 1")
        print("  Vivre Cards: 1")
        print(f"  Crew Actions: {len(actions)}")
        print("  Dial Config: 1")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

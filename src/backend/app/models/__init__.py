from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


# Import all models so Alembic can detect them
from app.models.build_artifact import BuildArtifact  # noqa: E402, F401
from app.models.crew_action import CrewAction  # noqa: E402, F401
from app.models.dial_config import DialConfig  # noqa: E402, F401
from app.models.health_check import HealthCheck  # noqa: E402, F401
from app.models.poneglyph import Poneglyph  # noqa: E402, F401
from app.models.shipwright_run import ShipwrightRun  # noqa: E402, F401
from app.models.user import User  # noqa: E402, F401
from app.models.validation_run import ValidationRun  # noqa: E402, F401
from app.models.vivre_card import VivreCard  # noqa: E402, F401
from app.models.voyage import Voyage, VoyagePlan  # noqa: E402, F401

"""Log Book REST API — record and recall per-repo cross-voyage memory.

Default-deny: every endpoint requires an authenticated user. Writes are
API-driven in this phase (an automatic write-back from completed voyages is a
noted follow-up).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.models import get_db
from app.models.user import User
from app.schemas.log_book import LogBookEntryCreate, LogBookEntryRead
from app.services.log_book_service import LogBookService

router = APIRouter(prefix="/log-book", tags=["log-book"])


async def get_log_book_service(
    session: AsyncSession = Depends(get_db),
) -> LogBookService:
    return LogBookService(session)


@router.get("", response_model=list[LogBookEntryRead])
async def recall_log_book(
    repo: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    service: LogBookService = Depends(get_log_book_service),
) -> list[LogBookEntryRead]:
    """Recall the crew's prior knowledge for a repository (most-recent-first)."""
    entries = await service.recall(repo, limit=limit)
    return [LogBookEntryRead.model_validate(e) for e in entries]


@router.post(
    "",
    response_model=LogBookEntryRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_log_book_entry(
    body: LogBookEntryCreate,
    user: User = Depends(get_current_user),
    service: LogBookService = Depends(get_log_book_service),
) -> LogBookEntryRead:
    """Record a new Log Book entry for a repository."""
    entry = await service.record(
        body.repo,
        body.author,
        body.kind,
        body.content,
        details=body.details,
        voyage_id=body.voyage_id,
    )
    return LogBookEntryRead.model_validate(entry)

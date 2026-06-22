"""LogBookService — read/write the Log Book (per-repo cross-voyage memory).

The Log Book persists learnings ACROSS voyages, keyed on a repository string
(``Voyage.target_repo``). The Captain recalls it when charting a course so the
crew doesn't re-learn a repo's layout, conventions, and gotchas every time.

Write path is API-driven in this phase. ``render_context`` produces a
prompt-injectable markdown block the Captain prepends to the planning task.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log_book import LogBookEntry

logger = logging.getLogger(__name__)


class LogBookError(Exception):
    """Raised when Log Book operations fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class LogBookService:
    """Records and recalls per-repo prior knowledge for the crew."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def reader(cls, session: AsyncSession) -> LogBookService:
        """Create an instance that only needs a DB session.

        The Log Book service is session-only (no dial router / mushi), so this
        mirrors ``CaptainService.reader`` purely for call-site consistency.
        """
        return cls(session)

    async def record(
        self,
        repo: str,
        author: str,
        kind: str,
        content: str,
        *,
        details: dict[str, object] | None = None,
        voyage_id: uuid.UUID | None = None,
    ) -> LogBookEntry:
        """Persist a new Log Book entry and return the committed row."""
        entry = LogBookEntry(
            repo=repo,
            author=author,
            kind=kind,
            content=content,
            details=details if details is not None else {},
            voyage_id=voyage_id,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def recall(
        self,
        repo: str,
        *,
        limit: int = 20,
        kinds: Sequence[str] | None = None,
    ) -> list[LogBookEntry]:
        """Return prior knowledge for ``repo``, most-recent-first.

        ``kinds`` optionally filters to a subset of the taxonomy.
        """
        stmt = select(LogBookEntry).where(LogBookEntry.repo == repo)
        if kinds:
            stmt = stmt.where(LogBookEntry.kind.in_(list(kinds)))
        stmt = stmt.order_by(LogBookEntry.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def render_context(self, repo: str, *, limit: int = 20) -> str:
        """Render recalled entries into a prompt-injectable markdown block.

        Returns ``""`` when there is nothing to recall so callers can no-op
        safely (the Captain only prepends a non-empty block).
        """
        entries = await self.recall(repo, limit=limit)
        if not entries:
            return ""

        lines = [f"## Log Book — prior knowledge for {repo}", ""]
        for entry in entries:
            lines.append(f"- ({entry.kind}) {entry.content}")
        return "\n".join(lines)

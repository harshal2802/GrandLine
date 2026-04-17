"""Shared helpers for crew agent LangGraphs."""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs commonly wrap JSON in."""
    text = text.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text

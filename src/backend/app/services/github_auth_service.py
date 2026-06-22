"""GithubAuthService — per-user GitHub via the device-code OAuth flow (Phase A3).

Today every git operation uses a single deployment-level ``github_api_token`` and
a fixed author identity. A3 lets each user connect THEIR OWN GitHub account through
GitHub's **device-code OAuth flow** (the same flow C0 chose for Claude Code), and
stows the resulting access token in the **Sea Chest** (Phase 0a, ``kind="github"``).
Later git ops (clone/push/PR) then run with the user's token + identity when
connected, falling back to the env token otherwise.

The flow is two steps the caller drives from the UI:

1. ``start_device_flow`` — POST ``github.com/login/device/code`` → a ``user_code``
   the user types at a ``verification_uri`` plus an opaque ``device_code`` the
   client polls with.
2. ``poll_device_flow`` — POST ``github.com/login/oauth/access_token`` until the
   user approves; on success fetch their ``login`` via ``GET {api_base}/user`` and
   ``SeaChestService.store`` the token under the ``@login`` label.

Security (NON-NEGOTIABLE): the access token (and ``device_code``/``user_code``) is
NEVER logged or returned by any endpoint — ``DeviceFlowStatus`` carries only the
GitHub ``login``. The hosts are FIXED (``github.com`` for the device flow,
``settings.github_api_base_url`` for the user lookup) — never derived from input.
``github_oauth_client_id`` is an env-only deployment setting; unset fails closed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.integrations import DeviceFlowStart, DeviceFlowStatus
from app.services.sea_chest_service import SeaChestService

logger = logging.getLogger(__name__)

# GitHub's device-flow endpoints live on the human-facing host (NOT the API host).
_DEVICE_CODE_URL = "https://github.com/login/device/code"
_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
# The OAuth scope we request — repo access for the user's git operations.
_SCOPE = "repo"
_GITHUB_KIND = "github"
_HTTP_TIMEOUT_SECONDS = 10.0
# GitHub device-flow "soft" errors: the user simply hasn't finished approving yet.
_PENDING_ERRORS = frozenset({"authorization_pending", "slow_down"})


class GithubAuthError(Exception):
    """Raised when the GitHub device flow cannot proceed (e.g. unconfigured)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class GithubAuthService:
    """Drive GitHub's device-code OAuth flow and vault the token in the Sea Chest."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def start_device_flow(self) -> DeviceFlowStart:
        """Begin the device flow: request a user code + device code from GitHub.

        Returns the ``user_code`` + ``verification_uri`` to SHOW the user, plus the
        opaque ``device_code`` the client polls with. Raises ``OAUTH_NOT_CONFIGURED``
        when ``github_oauth_client_id`` is unset — the flow cannot start without it.
        """
        client_id = self._settings.github_oauth_client_id
        if not client_id:
            raise GithubAuthError(
                "OAUTH_NOT_CONFIGURED",
                "GitHub OAuth is not configured (github_oauth_client_id unset)",
            )

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _DEVICE_CODE_URL,
                headers={"Accept": "application/json"},
                data={"client_id": client_id, "scope": _SCOPE},
            )

        if response.status_code != 200:
            raise GithubAuthError(
                "DEVICE_FLOW_FAILED",
                f"GitHub device-code request failed (HTTP {response.status_code})",
            )

        data: dict[str, Any] = response.json()
        if "device_code" not in data or "user_code" not in data:
            raise GithubAuthError(
                "DEVICE_FLOW_FAILED",
                "GitHub device-code response missing required fields",
            )

        return DeviceFlowStart(
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            device_code=data["device_code"],
            interval=int(data.get("interval", 5)),
            expires_in=int(data.get("expires_in", 900)),
        )

    async def poll_device_flow(self, user_id: Any, device_code: str) -> DeviceFlowStatus:
        """Poll for the access token; on approval, vault it and report the login.

        - ``authorization_pending``/``slow_down`` → status ``pending`` (keep polling).
        - success → fetch the user's ``login`` and ``SeaChestService.store`` the
          token under the ``@login`` label; status ``connected`` carrying ONLY the
          login (NEVER the token).
        - ``expired_token``/``access_denied``/anything else → status ``error``.
        The token is never logged or returned.
        """
        client_id = self._settings.github_oauth_client_id
        if not client_id:
            raise GithubAuthError(
                "OAUTH_NOT_CONFIGURED",
                "GitHub OAuth is not configured (github_oauth_client_id unset)",
            )

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            token_resp = await client.post(
                _ACCESS_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": _DEVICE_GRANT_TYPE,
                },
            )

        token_data: dict[str, Any] = token_resp.json()
        error = token_data.get("error")
        if error in _PENDING_ERRORS:
            return DeviceFlowStatus(status="pending")

        access_token = token_data.get("access_token")
        if error or not access_token:
            # expired_token / access_denied / unexpected — surface the code only,
            # never the token (there isn't one).
            return DeviceFlowStatus(status="error", error=error or "no_access_token")

        login = await self._fetch_login(access_token)

        sea_chest = SeaChestService(self._session, self._settings)
        await sea_chest.store(user_id, _GITHUB_KIND, access_token, label=f"@{login}")

        return DeviceFlowStatus(status="connected", login=login)

    async def _fetch_login(self, access_token: str) -> str:
        """Resolve the connecting user's GitHub ``login`` via ``GET {api_base}/user``.

        The host is ALWAYS ``settings.github_api_base_url`` — never derived from
        untrusted input. The bearer token is passed but never logged.
        """
        base = self._settings.github_api_base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{base}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )

        if response.status_code != 200:
            raise GithubAuthError(
                "USER_LOOKUP_FAILED",
                f"GitHub user lookup failed (HTTP {response.status_code})",
            )

        login = response.json().get("login")
        if not login:
            raise GithubAuthError("USER_LOOKUP_FAILED", "GitHub user response missing login")
        return str(login)


__all__ = ["GithubAuthError", "GithubAuthService"]

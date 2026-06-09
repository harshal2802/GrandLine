from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import tempfile
from collections.abc import AsyncIterator
from typing import Any

from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "claude_code"

# Tail of stderr/output included in ProviderError messages.
_ERROR_TAIL_CHARS = 500


def _build_prompt(messages: list[dict[str, str]]) -> tuple[str, str | None]:
    """Flatten chat messages into a single CLI prompt + optional system prompt.

    The Claude Code CLI takes one prompt string (via stdin in print mode), so
    multi-turn history is rendered as a Human/Assistant transcript. System
    messages are pulled out and passed via --append-system-prompt.
    """
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    convo = [m for m in messages if m.get("role") != "system"]

    if len(convo) == 1 and convo[0].get("role") == "user":
        prompt = convo[0]["content"]
    else:
        lines = []
        for m in convo:
            label = "Assistant" if m.get("role") == "assistant" else "Human"
            lines.append(f"{label}: {m['content']}")
        prompt = "\n\n".join(lines)

    system = "\n\n".join(system_parts) if system_parts else None
    return prompt, system


class ClaudeCodeAdapter(ProviderAdapter):
    """Adapter that runs completions through the Claude Code CLI (`claude -p`).

    Uses the CLI's non-interactive print mode, so it works with a Claude
    subscription (`claude` login / CLAUDE_CODE_OAUTH_TOKEN) as well as an
    ANTHROPIC_API_KEY — no key needs to be configured in GrandLine itself.

    Notes:
    - `temperature` is not supported by the CLI and is ignored.
    - `max_tokens` is forwarded via CLAUDE_CODE_MAX_OUTPUT_TOKENS.
    - Runs with --max-turns (default 1) so the gateway behaves as a text
      completion endpoint rather than an autonomous agent.
    """

    def __init__(
        self,
        model: str,
        cli_path: str = "claude",
        timeout_seconds: int = 300,
        max_turns: int = 1,
        workspace: str | None = None,
        extra_args: str = "",
    ) -> None:
        self._model = model
        self._cli_path = cli_path
        self._timeout_seconds = timeout_seconds
        self._max_turns = max_turns
        # Never run in the backend's own cwd: the CLI's read-only file tools
        # would otherwise be able to see backend source and config.
        self._workspace = workspace or tempfile.gettempdir()
        self._extra_args = shlex.split(extra_args) if extra_args else []
        self._rate_limited = False

    def _command(self, output_format: str, system: str | None) -> list[str]:
        cmd = [
            self._cli_path,
            "--print",
            "--output-format",
            output_format,
            "--model",
            self._model,
            "--max-turns",
            str(self._max_turns),
        ]
        if output_format == "stream-json":
            # The CLI requires --verbose for stream-json in print mode.
            cmd.append("--verbose")
        if system:
            cmd.extend(["--append-system-prompt", system])
        cmd.extend(self._extra_args)
        return cmd

    def _env(self, request: CompletionRequest) -> dict[str, str]:
        env = dict(os.environ)
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(request.max_tokens)
        # Server context: no autoupdater or other non-essential traffic.
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return env

    def _note_rate_limit(self, text: str) -> None:
        lowered = text.lower()
        if "rate limit" in lowered or "429" in lowered:
            self._rate_limited = True

    async def _spawn(
        self, output_format: str, request: CompletionRequest
    ) -> tuple[asyncio.subprocess.Process, bytes]:
        prompt, system = _build_prompt(request.messages)
        cmd = self._command(output_format, system)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(request),
                cwd=self._workspace,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                f"Claude Code CLI not found at {self._cli_path!r}. "
                "Install it with: npm install -g @anthropic-ai/claude-code"
            ) from exc
        return proc, prompt.encode()

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        proc, prompt = await self._spawn("json", request)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt), timeout=self._timeout_seconds
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise ProviderError(
                f"Claude Code CLI timed out after {self._timeout_seconds}s"
            ) from exc

        err_text = stderr.decode(errors="replace")
        if proc.returncode != 0:
            self._note_rate_limit(err_text)
            raise ProviderError(
                f"Claude Code CLI exited with code {proc.returncode}: "
                f"{err_text[-_ERROR_TAIL_CHARS:]}"
            )

        try:
            data: dict[str, Any] = json.loads(stdout.decode(errors="replace"))
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Claude Code CLI returned invalid JSON: {exc}") from exc

        result_text = data.get("result") or ""
        if data.get("is_error") or data.get("subtype") != "success":
            self._note_rate_limit(f"{err_text} {result_text}")
            raise ProviderError(
                f"Claude Code CLI error ({data.get('subtype', 'unknown')}): "
                f"{str(result_text)[-_ERROR_TAIL_CHARS:]}"
            )

        usage: dict[str, Any] = data.get("usage") or {}
        # Cached tokens are billed separately but are still part of the prompt.
        prompt_tokens = (
            int(usage.get("input_tokens", 0))
            + int(usage.get("cache_creation_input_tokens", 0))
            + int(usage.get("cache_read_input_tokens", 0))
        )
        completion_tokens = int(usage.get("output_tokens", 0))
        # modelUsage (newer CLIs) is keyed by the resolved model ID, which is
        # more precise than the alias we were configured with (e.g. "sonnet").
        model = next(iter(data.get("modelUsage") or {}), self._model)

        return CompletionResult(
            content=result_text,
            provider=PROVIDER_NAME,
            model=model,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        proc, prompt = await self._spawn("stream-json", request)
        assert proc.stdin is not None and proc.stdout is not None

        async def _run() -> AsyncIterator[str]:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt)
            await proc.stdin.drain()
            proc.stdin.close()

            yielded = False
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("type") == "assistant":
                    content = (event.get("message") or {}).get("content") or []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text") or ""
                            if text:
                                yielded = True
                                yield text
                elif event.get("type") == "result":
                    result_text = str(event.get("result") or "")
                    if event.get("is_error"):
                        self._note_rate_limit(result_text)
                        raise ProviderError(
                            f"Claude Code CLI error ({event.get('subtype', 'unknown')}): "
                            f"{result_text[-_ERROR_TAIL_CHARS:]}"
                        )
                    # Older CLIs may emit the result text only on this event.
                    if not yielded and result_text:
                        yield result_text
                    break

        try:
            gen = _run()
            while True:
                try:
                    token = await asyncio.wait_for(gen.__anext__(), timeout=self._timeout_seconds)
                except StopAsyncIteration:
                    break
                yield token

            await asyncio.wait_for(proc.wait(), timeout=self._timeout_seconds)
            if proc.returncode != 0:
                stderr = b"" if proc.stderr is None else await proc.stderr.read()
                err_text = stderr.decode(errors="replace")
                self._note_rate_limit(err_text)
                raise ProviderError(
                    f"Claude Code CLI exited with code {proc.returncode}: "
                    f"{err_text[-_ERROR_TAIL_CHARS:]}"
                )
        except TimeoutError as exc:
            raise ProviderError(
                f"Claude Code CLI timed out after {self._timeout_seconds}s"
            ) from exc
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=self._rate_limited)

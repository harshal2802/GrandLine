from __future__ import annotations

from typing import Any

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.core.config import Settings
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.anthropic import AnthropicAdapter
from app.dial_system.adapters.base import ProviderAdapter
from app.dial_system.adapters.claude_code import ClaudeCodeAdapter
from app.dial_system.adapters.ollama import OllamaAdapter
from app.dial_system.adapters.openai import OpenAIAdapter
from app.dial_system.rate_limiter import RateLimiter
from app.dial_system.router import DialSystemRouter
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole
from app.schemas.dial_config import resolve_claude_code_role_config

# Sensible per-provider default models, used when a fallback_chain entry is a
# bare provider string with no explicit model. The primary role's model is never
# reused for a fallback on a different vendor — that sends e.g. a Claude model id
# to OpenAI and 404s (see #50). Prefer the object form to be explicit.
_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "ollama": "llama3",
    "claude_code": "sonnet",
    "claude-code": "sonnet",
}


def _default_model_for(provider: str, settings: Settings) -> str:
    """Resolve a default model for a bare-string fallback entry.

    Uses the configured default model for the deployment's default provider so a
    custom ``GRANDLINE_DIAL_DEFAULT_MODEL`` is honored; otherwise a known-good
    per-provider default. Unknown providers raise (they have no valid model).
    """
    if provider == settings.dial_default_provider and settings.dial_default_model:
        return settings.dial_default_model
    model = _PROVIDER_DEFAULT_MODELS.get(provider)
    if model is None:
        raise ValueError(
            f"No default model known for fallback provider {provider!r}; "
            "specify it explicitly as {'provider': ..., 'model': ...}"
        )
    return model


def _resolve_fallback_entry(entry: Any, settings: Settings) -> tuple[str, str]:
    """Return ``(provider, model)`` for one ``fallback_chain`` entry.

    Accepts two shapes:
      * bare string ``"openai"`` — back-compat; resolves to the provider's
        default model rather than the primary role's model.
      * object ``{"provider": "openai", "model": "gpt-4o"}`` — explicit and
        recommended; ``model`` may be omitted to use the provider default.
    """
    if isinstance(entry, str):
        return entry, _default_model_for(entry, settings)
    if isinstance(entry, dict):
        provider = entry.get("provider")
        if not provider:
            raise ValueError(f"Fallback entry missing 'provider': {entry!r}")
        model = entry.get("model") or _default_model_for(provider, settings)
        return provider, model
    raise ValueError(f"Invalid fallback entry (expected string or object): {entry!r}")


def create_adapter(
    provider: str,
    model: str,
    settings: Settings,
    role_cfg: dict[str, Any] | None = None,
) -> ProviderAdapter:
    if provider == "anthropic":
        return AnthropicAdapter(
            client=AsyncAnthropic(api_key=settings.anthropic_api_key), model=model
        )
    elif provider == "openai":
        return OpenAIAdapter(client=AsyncOpenAI(api_key=settings.openai_api_key), model=model)
    elif provider == "ollama":
        return OllamaAdapter(
            client=httpx.AsyncClient(),
            model=model,
            base_url=settings.ollama_base_url,
        )
    elif provider in ("claude_code", "claude-code"):
        # Per-role safe knob (Phase C1): max_turns may come from the role's
        # mapping entry; host/auth knobs stay env-level. Falls back to the env
        # default on any missing/invalid per-role value.
        max_turns = resolve_claude_code_role_config(role_cfg).max_turns or (
            settings.claude_code_max_turns
        )
        return ClaudeCodeAdapter(
            model=model,
            cli_path=settings.claude_code_cli_path,
            timeout_seconds=settings.claude_code_timeout_seconds,
            max_turns=max_turns,
            workspace=settings.claude_code_workspace or None,
            extra_args=settings.claude_code_extra_args,
        )
    else:
        raise ValueError(f"Unknown provider: {provider!r}")


def build_router_from_config(
    config: DialConfig,
    settings: Settings,
    mushi: DenDenMushi,
    rate_limiter: RateLimiter,
) -> DialSystemRouter:
    role_mapping: dict[CrewRole, ProviderAdapter] = {}
    fallback_chains: dict[CrewRole, list[ProviderAdapter]] = {}

    mapping: dict[str, Any] = config.role_mapping or {}
    for role_str, provider_cfg in mapping.items():
        role = CrewRole(role_str)
        if not isinstance(provider_cfg, dict):
            raise ValueError(f"Invalid config for role {role_str}: expected dict")
        provider = provider_cfg.get("provider")
        model = provider_cfg.get("model")
        if not provider or not model:
            raise ValueError(f"Missing 'provider' or 'model' in config for role {role_str}")
        role_mapping[role] = create_adapter(provider, model, settings, role_cfg=provider_cfg)

    chains: dict[str, Any] = config.fallback_chain or {}
    for role_str, fallback_entries in chains.items():
        role = CrewRole(role_str)
        adapters: list[ProviderAdapter] = []
        for entry in fallback_entries:
            provider, model = _resolve_fallback_entry(entry, settings)
            adapters.append(create_adapter(provider, model, settings))
        fallback_chains[role] = adapters

    return DialSystemRouter(
        role_mapping=role_mapping,
        fallback_chains=fallback_chains,
        mushi=mushi,
        voyage_id=config.voyage_id,
        rate_limiter=rate_limiter,
    )

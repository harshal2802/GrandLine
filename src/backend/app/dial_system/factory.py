from __future__ import annotations

from typing import Any

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.core.config import Settings
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.anthropic import AnthropicAdapter
from app.dial_system.adapters.base import ProviderAdapter
from app.dial_system.adapters.ollama import OllamaAdapter
from app.dial_system.adapters.openai import OpenAIAdapter
from app.dial_system.rate_limiter import RateLimiter
from app.dial_system.router import DialSystemRouter
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole


def create_adapter(provider: str, model: str, settings: Settings) -> ProviderAdapter:
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
        role_mapping[role] = create_adapter(provider, model, settings)

    chains: dict[str, Any] = config.fallback_chain or {}
    for role_str, fallback_providers in chains.items():
        role = CrewRole(role_str)
        adapters: list[ProviderAdapter] = []
        default_model = mapping.get(role_str, {}).get("model", "default")
        for fb_provider in fallback_providers:
            adapters.append(create_adapter(fb_provider, default_model, settings))
        fallback_chains[role] = adapters

    return DialSystemRouter(
        role_mapping=role_mapping,
        fallback_chains=fallback_chains,
        mushi=mushi,
        voyage_id=config.voyage_id,
        rate_limiter=rate_limiter,
    )

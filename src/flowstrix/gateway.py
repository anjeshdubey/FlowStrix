"""
FlowStrix Gateway — LLM client factory.

Supports Together AI, Groq, Gemini, and Anthropic via their OpenAI-compatible APIs.

Environment variables:
    TOGETHER_API_KEY            — Together AI API key (default/primary — paid tier, no free-tier throttling)
    GROQ_API_KEY                — Groq API key (first fallback)
    GEMINI_API_KEY              — Google Gemini API key (second fallback)
    ANTHROPIC_API_KEY           — Anthropic API key (third fallback — most expensive, last resort)
    FLOWSTRIX_MODEL             — Override default model (e.g. gemini-2.5-flash, llama-3.3-70b-versatile)
    UPSTASH_REDIS_REST_URL      — Upstash Redis REST endpoint (optional, enables response caching)
    UPSTASH_REDIS_REST_TOKEN    — Upstash Redis REST token (optional, enables response caching)

ChatGateway tries providers in that order — Together AI, then Groq, then
Gemini, then Anthropic — automatically failing over on a rate-limit or
provider error. Together AI sits first because it's a metered paid tier
with no free-tier rate-limit games (unlike Groq/Gemini free tiers, which
throttle unpredictably under demand). Anthropic sits last because it's the
most expensive per call; it only gets used when everything else is down.
Recruiter-facing demos should never see a raw API failure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# Base URLs
TOGETHER_BASE_URL = "https://api.together.xyz/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"

# Default models
DEFAULT_TOGETHER_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"

# Model alias mapping — short names → full model IDs
# Note: Together AI only offers Llama 3.1 8B Instruct as a dedicated
# (hourly-billed) endpoint, not serverless — so no 8B alias here. Only
# list models confirmed serverless on Together's model catalog.
TOGETHER_MODEL_ALIASES: dict[str, str] = {
    "together-llama-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "qwen-7b": "Qwen/Qwen2.5-7B-Instruct-Turbo",
}
GROQ_MODEL_ALIASES: dict[str, str] = {
    "llama-70b": "llama-3.3-70b-versatile",
    "llama-8b": "llama-3.1-8b-instant",
    "mixtral": "mixtral-8x7b-32768",
    "gemma-9b": "gemma2-9b-it",
}
GEMINI_MODEL_ALIASES: dict[str, str] = {
    "gemini-flash": "gemini-3.5-flash",
    "gemini-pro": "gemini-3.5-pro",
    "gemini-2.5-flash": "gemini-3.5-flash",  # Fallback for old references
    "gemini-2.5-pro": "gemini-3.5-pro",  # Fallback for old references
}
ANTHROPIC_MODEL_ALIASES: dict[str, str] = {
    "claude-sonnet": "claude-sonnet-5",
    "claude-opus": "claude-opus-4-8",
    "claude-haiku": "claude-haiku-4-5-20251001",
}
MODEL_ALIASES: dict[str, str] = {
    **TOGETHER_MODEL_ALIASES,
    **GROQ_MODEL_ALIASES,
    **GEMINI_MODEL_ALIASES,
    **ANTHROPIC_MODEL_ALIASES,
}

# Errors worth retrying against the next provider in the chain.
RETRYABLE_ERRORS = (
    RateLimitError,
    APIStatusError,
    APITimeoutError,
    APIConnectionError,
    APIError,
)

# Demo prompts are static (hardcoded per step), so a cached response stays
# valid until the journey spec itself changes — cache for 30 days.
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


def _resolve_provider_model(
    alias_map: dict[str, str], default_model: str, override: str
) -> str:
    """Resolve FLOWSTRIX_MODEL for one provider's alias map.

    If the override names a model belonging to a *different* provider (e.g.
    FLOWSTRIX_MODEL=llama-70b while building the Gemini config), ignore it
    here and fall back to this provider's default — a fallback provider
    should never be forced onto another provider's model id.
    """
    if not override:
        return default_model
    if override in alias_map:
        return alias_map[override]
    if override in MODEL_ALIASES:
        return default_model  # Belongs to the other provider.
    return override  # Unknown string — treat as an explicit model id for this provider.


@dataclass
class GatewayConfig:
    """Configuration for the LLM gateway connection."""

    base_url: str
    auth_token: str
    model: str
    provider: str
    cert_path: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Load gateway config from environment variables.

        Picks the first configured provider in priority order: Together AI
        (default, metered paid tier — no free-tier throttling), then Groq,
        then Gemini, then Anthropic.
        """
        chain = cls.chain_from_env()
        return chain[0]

    @classmethod
    def chain_from_env(cls) -> list["GatewayConfig"]:
        """Build a priority-ordered provider chain from whichever API keys are set.

        Order: Together AI (default) → Groq → Gemini → Anthropic. Together AI
        leads because it's a metered paid tier with no free-tier rate-limit
        games. Anthropic is last because it's the most expensive per call —
        it's an emergency-only fallback, not something a demo should lean on
        for routine traffic. Used by ChatGateway so a rate-limited/erroring
        provider automatically fails over to the next one.
        """
        together_key = os.environ.get("TOGETHER_API_KEY", "")
        groq_key = os.environ.get("GROQ_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        model_override = os.environ.get("FLOWSTRIX_MODEL", "")

        chain: list["GatewayConfig"] = []
        if together_key:
            model = _resolve_provider_model(
                TOGETHER_MODEL_ALIASES, DEFAULT_TOGETHER_MODEL, model_override
            )
            chain.append(
                cls(
                    base_url=TOGETHER_BASE_URL,
                    auth_token=together_key,
                    model=model,
                    provider="together",
                )
            )
        if groq_key:
            model = _resolve_provider_model(
                GROQ_MODEL_ALIASES, DEFAULT_GROQ_MODEL, model_override
            )
            chain.append(
                cls(
                    base_url=GROQ_BASE_URL,
                    auth_token=groq_key,
                    model=model,
                    provider="groq",
                )
            )
        if gemini_key:
            model = _resolve_provider_model(
                GEMINI_MODEL_ALIASES, DEFAULT_GEMINI_MODEL, model_override
            )
            chain.append(
                cls(
                    base_url=GEMINI_BASE_URL,
                    auth_token=gemini_key,
                    model=model,
                    provider="gemini",
                )
            )
        if anthropic_key:
            model = _resolve_provider_model(
                ANTHROPIC_MODEL_ALIASES, DEFAULT_ANTHROPIC_MODEL, model_override
            )
            chain.append(
                cls(
                    base_url=ANTHROPIC_BASE_URL,
                    auth_token=anthropic_key,
                    model=model,
                    provider="anthropic",
                )
            )

        if not chain:
            raise GatewayConfigError(
                "No API key found. Set TOGETHER_API_KEY, GROQ_API_KEY, "
                "GEMINI_API_KEY, or ANTHROPIC_API_KEY in your .env file.\n"
                "Get a Together AI key at: https://api.together.ai\n"
                "Get a Groq key at: https://console.groq.com\n"
                "Get a Gemini key at: https://aistudio.google.com\n"
                "Get an Anthropic key at: https://console.anthropic.com"
            )
        return chain


class GatewayConfigError(Exception):
    """Raised when gateway configuration is missing or invalid."""

    pass


def create_client(config: GatewayConfig | None = None) -> OpenAI:
    """Create an OpenAI-compatible client.

    Args:
        config: Gateway configuration. If None, loads from environment.

    Returns:
        Configured OpenAI client pointing at the selected provider.
    """
    if config is None:
        config = GatewayConfig.from_env()

    return OpenAI(
        api_key=config.auth_token,
        base_url=config.base_url,
    )


def resolve_model(model_name: str) -> str:
    """Resolve a short model name to the full provider model ID."""
    return MODEL_ALIASES.get(model_name, model_name)


def resolve_chain(primary: GatewayConfig | None) -> list[GatewayConfig]:
    """Build the provider chain a ChatGateway should use.

    If `primary` is None, use every provider configured in the environment
    (priority order from chain_from_env()). If a specific `primary` config
    was passed in (e.g. a caller explicitly picked one provider), still look
    for one additional, differently-provided fallback in the environment —
    a pinned primary should still fail over rather than hard-erroring.
    """
    if primary is None:
        return GatewayConfig.chain_from_env()

    chain = [primary]
    try:
        for cfg in GatewayConfig.chain_from_env():
            if cfg.provider != primary.provider:
                chain.append(cfg)
                break
    except GatewayConfigError:
        pass
    return chain


# --- Upstash Redis cache (exact-match, keyed by request payload) ---


def _cache_command(*command: str | int) -> Any:
    """Execute a single Redis command via the Upstash REST API.

    Returns None (cache disabled or unreachable) instead of raising — caching
    is a latency/cost optimization, never a hard dependency for serving a demo.
    """
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        return None

    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=list(command),
            timeout=2.0,
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except httpx.HTTPError as e:
        logger.warning("Upstash cache request failed, continuing without cache: %s", e)
        return None


def _cache_key(
    model: str, messages: list[dict[str, str]], temperature: float, max_tokens: int
) -> str:
    """Deterministic cache key for a chat completion request.

    Demo journeys use hardcoded per-step prompts, so identical inputs
    (same step, same resolved context) hash to the same key across every
    recruiter session.
    """
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"flowstrix:llm:{digest}"


class ChatGateway:
    """LLM chat completion gateway with automatic provider fallback + response caching.

    Wraps a priority-ordered list of GatewayConfigs (e.g. [groq, gemini, anthropic]).
    On each call: check the Upstash cache first; on a miss, try each provider
    in order until one succeeds, then cache the result. If Upstash isn't
    configured, caching is silently skipped — the fallback chain still works.
    """

    def __init__(self, configs: list[GatewayConfig]):
        if not configs:
            raise GatewayConfigError(
                "ChatGateway requires at least one provider config"
            )
        self._chain = [(cfg.provider, create_client(cfg), cfg.model) for cfg in configs]

    @classmethod
    def from_env(cls) -> "ChatGateway":
        return cls(GatewayConfig.chain_from_env())

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> str:
        """Run a chat completion, serving from cache when possible.

        Cache key is scoped to the primary provider's model so a fallback
        response (from a different model) is never persisted as if it came
        from the primary — avoids caching a lower-quality answer under the
        primary's key.
        """
        primary_model = self._chain[0][2]
        key = _cache_key(primary_model, messages, temperature, max_tokens)

        cached = _cache_command("GET", key)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for provider, client, model in self._chain:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = response.choices[0].message.content or ""
                if model == primary_model:
                    _cache_command("SETEX", key, CACHE_TTL_SECONDS, text)
                return text
            except RETRYABLE_ERRORS as e:
                logger.warning(
                    "Provider %s failed, trying next in chain: %s", provider, e
                )
                last_error = e
                continue

        raise GatewayConfigError(
            f"All providers in the chain failed. Last error: {last_error}"
        )

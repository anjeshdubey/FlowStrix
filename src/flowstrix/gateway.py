"""
FlowStrix Gateway — LLM client factory.

Supports both Groq and Gemini via their OpenAI-compatible APIs.

Environment variables:
    GEMINI_API_KEY      — Google Gemini API key (recommended)
    GROQ_API_KEY        — Groq API key
    FLOWSTRIX_MODEL     — Override default model (e.g. gemini-2.5-flash, llama-3.3-70b-versatile)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from openai import OpenAI


# Base URLs
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Default models
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Model alias mapping — short names → full model IDs
MODEL_ALIASES: dict[str, str] = {
    # Gemini Aliases
    "gemini-flash": "gemini-3.5-flash",
    "gemini-pro": "gemini-3.5-pro",
    "gemini-2.5-flash": "gemini-3.5-flash",  # Fallback for old references
    "gemini-2.5-pro": "gemini-3.5-pro",      # Fallback for old references
    # Groq Aliases
    "llama-70b": "llama-3.3-70b-versatile",
    "llama-8b": "llama-3.1-8b-instant",
    "mixtral": "mixtral-8x7b-32768",
    "gemma-9b": "gemma2-9b-it",
}


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

        Detects if GEMINI_API_KEY or GROQ_API_KEY is configured.
        """
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        groq_key = os.environ.get("GROQ_API_KEY", "")

        if gemini_key:
            provider = "gemini"
            auth_token = gemini_key
            base_url = GEMINI_BASE_URL
            default_model = DEFAULT_GEMINI_MODEL
        elif groq_key:
            provider = "groq"
            auth_token = groq_key
            base_url = GROQ_BASE_URL
            default_model = DEFAULT_GROQ_MODEL
        else:
            raise GatewayConfigError(
                "No API key found. Set GEMINI_API_KEY or GROQ_API_KEY in your .env file.\n"
                "Get a Gemini key at: https://aistudio.google.com\n"
                "Get a Groq key at: https://console.groq.com"
            )

        model = os.environ.get("FLOWSTRIX_MODEL", default_model)
        model = MODEL_ALIASES.get(model, model)

        return cls(
            base_url=base_url,
            auth_token=auth_token,
            model=model,
            provider=provider,
        )


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

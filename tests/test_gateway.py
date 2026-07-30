"""Tests for the ChatGateway cache + provider-fallback wrapper.

Uses fake OpenAI clients and a fake Upstash backend (in-memory dict) so no
real network calls happen.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError

from flowstrix import gateway as gw
from flowstrix.gateway import ChatGateway, GatewayConfig


def make_client_response(
    text: str, tokens_in: int | None = None, tokens_out: int | None = None
) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=text))]
    if tokens_in is None and tokens_out is None:
        # Providers may omit usage entirely. A bare MagicMock would hand back
        # auto-created attributes, so pin it to None to model that case.
        response.usage = None
    else:
        response.usage = MagicMock(
            prompt_tokens=tokens_in, completion_tokens=tokens_out
        )
    return response


@pytest.fixture
def fake_upstash(monkeypatch):
    """In-memory stand-in for the Upstash REST API."""
    store: dict[str, str] = {}

    def fake_command(*command):
        op = command[0]
        if op == "GET":
            return store.get(command[1])
        if op == "SETEX":
            _, key, _ttl, value = command
            store[key] = value
            return "OK"
        raise ValueError(f"unexpected command {command}")

    monkeypatch.setattr(gw, "_cache_command", fake_command)
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://fake.upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "fake-token")
    return store


def make_gateway(monkeypatch, clients: dict[str, MagicMock]) -> ChatGateway:
    """Build a ChatGateway whose OpenAI clients are pre-made mocks."""
    configs = [
        GatewayConfig(
            base_url="http://x", auth_token="t", model=f"{p}-model", provider=p
        )
        for p in clients
    ]
    monkeypatch.setattr(gw, "create_client", lambda cfg: clients[cfg.provider])
    return ChatGateway(configs)


def test_cache_hit_never_calls_llm(monkeypatch, fake_upstash):
    """A plain-string cache entry (the pre-usage format) still serves."""
    primary = MagicMock()
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    messages = [{"role": "user", "content": "hi"}]
    fake_upstash[gw._cache_key("gemini-model", messages, 0.3, 512)] = "cached reply"

    result = gateway.complete(messages)

    assert result == "cached reply"
    primary.chat.completions.create.assert_not_called()


def test_legacy_cache_entry_reports_no_usage(monkeypatch, fake_upstash):
    """Entries written before usage tracking decode with tokens unknown.

    They must come back as None rather than 0 — a trace should show "unknown",
    not claim the call was free.
    """
    primary = MagicMock()
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    messages = [{"role": "user", "content": "hi"}]
    fake_upstash[gw._cache_key("gemini-model", messages, 0.3, 512)] = "cached reply"

    result = gateway.complete_detailed(messages)

    assert result.text == "cached reply"
    assert result.cached is True
    assert result.model == "gemini-model"
    assert result.tokens_in is None
    assert result.tokens_out is None
    assert result.usage is None


def test_cache_miss_calls_primary_and_populates_cache(monkeypatch, fake_upstash):
    primary = MagicMock()
    primary.chat.completions.create.return_value = make_client_response("fresh reply")
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    messages = [{"role": "user", "content": "hi"}]
    result = gateway.complete(messages)

    assert result == "fresh reply"

    # Cache entries are a JSON envelope now, not the bare text.
    key = gw._cache_key("gemini-model", messages, 0.3, 512)
    assert json.loads(fake_upstash[key])["text"] == "fresh reply"

    # Second call should now be served from cache, not the client again.
    primary.chat.completions.create.reset_mock()
    result2 = gateway.complete(messages)
    assert result2 == "fresh reply"
    primary.chat.completions.create.assert_not_called()


def test_usage_is_captured_from_provider_response(monkeypatch, fake_upstash):
    primary = MagicMock()
    primary.chat.completions.create.return_value = make_client_response(
        "fresh reply", tokens_in=128, tokens_out=64
    )
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    result = gateway.complete_detailed([{"role": "user", "content": "hi"}])

    assert result.text == "fresh reply"
    assert result.tokens_in == 128
    assert result.tokens_out == 64
    assert result.usage == {"tokens_in": 128, "tokens_out": 64}
    assert result.model == "gemini-model"
    assert result.provider == "gemini"
    assert result.cached is False


def test_usage_survives_a_cache_round_trip(monkeypatch, fake_upstash):
    """A cache hit still reports what the original call cost."""
    primary = MagicMock()
    primary.chat.completions.create.return_value = make_client_response(
        "fresh reply", tokens_in=200, tokens_out=25
    )
    gateway = make_gateway(monkeypatch, {"gemini": primary})
    messages = [{"role": "user", "content": "hi"}]

    gateway.complete_detailed(messages)
    primary.chat.completions.create.reset_mock()

    cached = gateway.complete_detailed(messages)

    primary.chat.completions.create.assert_not_called()
    assert cached.cached is True
    assert cached.tokens_in == 200
    assert cached.tokens_out == 25
    assert cached.model == "gemini-model"


def test_missing_usage_degrades_to_none(monkeypatch, fake_upstash):
    """Providers that omit usage must not break the call."""
    primary = MagicMock()
    primary.chat.completions.create.return_value = make_client_response("fresh reply")
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    result = gateway.complete_detailed([{"role": "user", "content": "hi"}])

    assert result.text == "fresh reply"
    assert result.usage is None


def test_fallback_response_reports_the_model_that_answered(
    monkeypatch, fake_upstash
):
    """On failover, usage and model must reflect the provider that succeeded."""
    primary = MagicMock()
    primary.chat.completions.create.side_effect = APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://x")
    )
    secondary = MagicMock()
    secondary.chat.completions.create.return_value = make_client_response(
        "fallback reply", tokens_in=10, tokens_out=5
    )
    gateway = make_gateway(monkeypatch, {"gemini": primary, "groq": secondary})

    result = gateway.complete_detailed([{"role": "user", "content": "hi"}])

    assert result.text == "fallback reply"
    assert result.provider == "groq"
    assert result.model == "groq-model"
    assert result.tokens_in == 10


def test_falls_back_to_next_provider_on_error(monkeypatch, fake_upstash):
    primary = MagicMock()
    primary.chat.completions.create.side_effect = APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://x")
    )
    secondary = MagicMock()
    secondary.chat.completions.create.return_value = make_client_response(
        "fallback reply"
    )

    gateway = make_gateway(monkeypatch, {"gemini": primary, "groq": secondary})

    messages = [{"role": "user", "content": "hi"}]
    result = gateway.complete(messages)

    assert result == "fallback reply"
    primary.chat.completions.create.assert_called_once()
    secondary.chat.completions.create.assert_called_once()

    # Fallback responses are not cached under the primary's key — a future
    # request should still try the primary again rather than being pinned
    # to the degraded fallback forever.
    key = gw._cache_key("gemini-model", messages, 0.3, 512)
    assert key not in fake_upstash


def test_all_providers_failing_raises(monkeypatch, fake_upstash):
    primary = MagicMock()
    primary.chat.completions.create.side_effect = APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://x")
    )
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    with pytest.raises(gw.GatewayConfigError):
        gateway.complete([{"role": "user", "content": "hi"}])


def test_chain_from_env_orders_groq_gemini_anthropic(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("FLOWSTRIX_MODEL", raising=False)

    chain = GatewayConfig.chain_from_env()

    assert [c.provider for c in chain] == ["groq", "gemini", "anthropic"]
    assert chain[2].base_url == gw.ANTHROPIC_BASE_URL
    assert chain[2].model == gw.DEFAULT_ANTHROPIC_MODEL


def test_falls_back_through_all_three_providers(monkeypatch, fake_upstash):
    groq = MagicMock()
    groq.chat.completions.create.side_effect = APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://x")
    )
    gemini = MagicMock()
    gemini.chat.completions.create.side_effect = APIConnectionError(
        message="boom", request=httpx.Request("POST", "http://x")
    )
    anthropic = MagicMock()
    anthropic.chat.completions.create.return_value = make_client_response(
        "claude reply"
    )

    gateway = make_gateway(
        monkeypatch, {"groq": groq, "gemini": gemini, "anthropic": anthropic}
    )

    result = gateway.complete([{"role": "user", "content": "hi"}])

    assert result == "claude reply"
    groq.chat.completions.create.assert_called_once()
    gemini.chat.completions.create.assert_called_once()
    anthropic.chat.completions.create.assert_called_once()


def test_no_upstash_configured_skips_cache_but_still_completes(monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    primary = MagicMock()
    primary.chat.completions.create.return_value = make_client_response(
        "no cache reply"
    )
    gateway = make_gateway(monkeypatch, {"gemini": primary})

    result = gateway.complete([{"role": "user", "content": "hi"}])
    assert result == "no cache reply"

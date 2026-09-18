"""Unified LLM access — routes to the Claude API (cloud) or gs65, a local
Ollama host reachable over Tailscale, based on settings.llm_provider.

Call sites use llm.complete(system=..., messages=[{role, content}, ...]) and
read .text / .tokens_in / .tokens_out, so they don't care which backend answered.
Ollama exposes an OpenAI-compatible Chat Completions API at /v1, so the local
path uses the openai SDK; the cloud path uses the anthropic SDK.
"""
from dataclasses import dataclass

from config import settings


@dataclass
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def configured() -> bool:
    """True when the selected provider has what it needs to make a call."""
    if settings.llm_provider == "local":
        return bool(settings.local_llm_base_url and settings.local_llm_model)
    return bool(settings.anthropic_api_key)


def complete(system: str, messages: list[dict], max_tokens: int,
             model: str | None = None, cache_system: bool = False) -> LLMResult:
    """Single completion. `messages` is a list of {"role", "content"} dicts
    (one user turn for most callers; a full convo for the resume coach).
    `model` overrides the default for the cloud backend (e.g. Haiku for bulk
    scoring); the local backend always uses gs65, so the override is ignored there.
    `cache_system` marks the system prompt as an Anthropic prompt-cache breakpoint —
    for callers that fire the SAME system text many times in a row (e.g. bulk role
    scoring), this turns every call after the first into a ~90%-cheaper cache read
    on its input tokens. No-op on the local backend (Ollama doesn't support it)."""
    if settings.llm_provider == "local":
        return _local(system, messages, max_tokens)
    return _anthropic(system, messages, max_tokens, model, cache_system)


def _anthropic(system: str, messages: list[dict], max_tokens: int,
               model: str | None = None, cache_system: bool = False) -> LLMResult:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    system_arg = (
        [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if cache_system else system
    )
    msg = client.messages.create(
        model=model or settings.claude_model,
        max_tokens=max_tokens,
        system=system_arg,
        messages=messages,
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return LLMResult(
        text, msg.usage.input_tokens, msg.usage.output_tokens,
        cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
    )


def _local(system: str, messages: list[dict], max_tokens: int) -> LLMResult:
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.local_llm_base_url,
        api_key=settings.local_llm_api_key or "ollama",
    )
    chat = [{"role": "system", "content": system}, *messages]
    resp = client.chat.completions.create(
        model=settings.local_llm_model,
        max_tokens=max_tokens,
        messages=chat,
    )
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return LLMResult(
        text,
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )

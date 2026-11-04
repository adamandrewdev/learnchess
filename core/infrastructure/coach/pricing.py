"""Model registry and prices, USD per million tokens (PLAN §6).

Fetched 4 Nov 2026:
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
  (Haiku: the <=100K-token-prompt tier; prompts here are a few thousand tokens)
- OpenAI: https://developers.openai.com/api/docs/pricing (Standard tier, <=272K context)

Meters: Anthropic has 4 (input, output, cache write, cache read). OpenAI has 3 (input,
cached input, output); it doesn't charge for cache writes, so cache_write == input. Don't use
OpenAI data-residency endpoints or Fast mode, or Anthropic `inference_geo`: each adds an uplift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str  # "anthropic" | "openai"
    label: str
    input: float
    output: float
    cache_write: float  # 5-minute cache write
    cache_read: float
    cache_write_1h: float = 0.0  # Anthropic 1-hour write (2x input); unused today
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    m.id: m
    for m in [
        ModelInfo(
            "claude-haiku-5-5", "anthropic", "Claude Haiku 5.5", 0.10, 0.50, 0.125, 0.01, 0.20
        ),
        ModelInfo(
            "claude-sonnet-5-5", "anthropic", "Claude Sonnet 5.5", 2.00, 10.00, 2.50, 0.10, 4.00
        ),
        ModelInfo(
            "gpt-4.1",
            "openai",
            "GPT-4.1",
            2.00,
            8.00,
            2.00,
            0.50,
            note="API shutdown reported for 14 Jan 2027 (secondary sources, unconfirmed)",
        ),
        ModelInfo(
            "gpt-5.1",
            "openai",
            "GPT-5.1",
            1.25,
            10.00,
            1.25,
            0.125,
            note="Reasoning model: hidden reasoning tokens are billed as output",
        ),
    ]
}


def cache_tokens(usage: dict) -> tuple[int, int, int]:
    """(cache_read, cache_write_5m, cache_write_1h) from LangChain `usage_metadata`.

    langchain-anthropic 1.7.10 sets `cache_creation` to 0 and moves the count to
    `ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` whenever Anthropic reports the
    cache lifetime (found in M1: writes were being billed as plain input). OpenAI reports neither.
    """
    d = usage.get("input_token_details") or {}
    w5 = d.get("ephemeral_5m_input_tokens") or 0
    w1 = d.get("ephemeral_1h_input_tokens") or 0
    if not (w5 or w1):
        w5 = d.get("cache_creation") or 0
    return d.get("cache_read") or 0, w5, w1


def cost_usd(model: str, usage: dict) -> float:
    """`usage` is LangChain's `usage_metadata` from an AIMessage.

    Both langchain-anthropic and langchain-openai report `input_tokens` INCLUDING cached tokens
    (checked in source), and `output_tokens` including any reasoning tokens.
    """
    p = MODELS[model]
    details = usage.get("input_token_details") or {}
    # langchain-openai prefixes cache keys with the tier for priority/flex calls, which these
    # prices don't cover. Fail loudly rather than undercount spend against the cap.
    tiered = [k for k in details if k.startswith(("priority_", "flex_"))]
    if tiered:
        raise ValueError(f"unpriced service tier in usage: {tiered}")
    read, w5, w1 = cache_tokens(usage)
    plain_input = usage.get("input_tokens", 0) - read - w5 - w1
    return (
        plain_input * p.input
        + usage.get("output_tokens", 0) * p.output
        + w5 * p.cache_write
        + w1 * (p.cache_write_1h or p.input)
        + read * p.cache_read
    ) / 1_000_000

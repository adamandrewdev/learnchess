"""Which models can actually be used right now, and how to build a chat model for one.

"Valid" means: the provider's key is set AND that provider's model-list endpoint (free, no
tokens billed) returns the model id. A retired model drops out of the list instead of failing
mid-game. Feeds the frontend model picker (PLAN D10).
"""

from __future__ import annotations

import logging
import os

import anthropic
import openai
from langchain_core.language_models import BaseChatModel

from core.infrastructure.coach.pricing import MODELS, ModelInfo

log = logging.getLogger(__name__)

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def _listed_ids(provider: str) -> set[str]:
    if provider == "anthropic":
        return {m.id for m in anthropic.Anthropic().models.list(limit=1000)}
    return {m.id for m in openai.OpenAI().models.list()}


def available_models() -> tuple[list[ModelInfo], dict[str, str]]:
    """(usable models, {provider: reason}) for each provider that couldn't be used."""
    usable, problems = [], {}
    for provider, env in KEY_ENV.items():
        if not os.environ.get(env):
            problems[provider] = f"{env} not set"
            continue
        try:
            listed = _listed_ids(provider)
        # Bad key, network down (both SDKs' connection errors subclass APIError).
        except (anthropic.APIError, openai.APIError) as exc:
            problems[provider] = f"model list failed: {type(exc).__name__}: {exc}"
            continue
        for m in MODELS.values():
            if m.provider != provider:
                continue
            if m.id in listed:
                usable.append(m)
            else:
                problems[m.id] = "not offered by provider for this key"
    for what, why in problems.items():
        log.warning("model unavailable: %s (%s)", what, why)
    return usable, problems


def chat_model(model_id: str) -> BaseChatModel:
    info = MODELS[model_id]
    if info.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_id, max_tokens=2048)
    from langchain_openai import ChatOpenAI

    if model_id.startswith("gpt-5"):
        # Reasoning model: keep thinking short; it's billed as output and adds latency.
        return ChatOpenAI(model=model_id, reasoning_effort="low", max_completion_tokens=4096)
    return ChatOpenAI(model=model_id, max_tokens=2048)

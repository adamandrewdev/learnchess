import pytest

from core.infrastructure.coach.pricing import cost_usd


def test_uncached_call():
    # 3,000 in + 400 out on Haiku 5.5: 3000*0.10/1e6 + 400*0.50/1e6 = 0.0003 + 0.0002
    usage = {"input_tokens": 3000, "output_tokens": 400}
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(0.0005)


def test_cached_tokens_are_not_double_billed():
    # LangChain's input_tokens INCLUDES cache reads/writes (verified in langchain-anthropic
    # 1.7.10 _create_usage_metadata). 3000 total = 500 plain + 2500 cache read.
    usage = {
        "input_tokens": 3000,
        "output_tokens": 400,
        "input_token_details": {"cache_read": 2500, "cache_creation": 0},
    }
    expected = (500 * 0.10 + 2500 * 0.01 + 400 * 0.50) / 1e6
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(expected)


def test_sonnet_cache_write():
    usage = {
        "input_tokens": 3000,
        "output_tokens": 400,
        "input_token_details": {"cache_read": None, "cache_creation": 2000},
    }
    expected = (1000 * 2.00 + 2000 * 2.50 + 400 * 10.00) / 1e6
    assert cost_usd("claude-sonnet-5-5", usage) == pytest.approx(expected)


def test_openai_cached_input():
    # OpenAI prompt_tokens include cached tokens; there is no cache-write charge.
    usage = {
        "input_tokens": 3000,
        "output_tokens": 1400,  # includes reasoning tokens
        "input_token_details": {"cache_read": 2048},
        "output_token_details": {"reasoning": 1000},
    }
    expected = (952 * 1.25 + 2048 * 0.125 + 1400 * 10.00) / 1e6
    assert cost_usd("gpt-5.1", usage) == pytest.approx(expected)


def test_unpriced_tier_fails_loudly():
    usage = {"input_tokens": 10, "output_tokens": 1, "input_token_details": {"flex_cache_read": 5}}
    with pytest.raises(ValueError, match="unpriced service tier"):
        cost_usd("gpt-5.1", usage)


def test_every_model_constructs_without_network():
    import os

    from core.infrastructure.coach.coach import Coach
    from core.infrastructure.coach.pricing import MODELS

    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-dummy")
    os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
    for model_id in MODELS:
        Coach(model=model_id)


def test_anthropic_cache_write_reported_by_ttl():
    # Shape langchain-anthropic 1.7.10 actually returns when the TTL breakdown is present:
    # generic cache_creation zeroed, tokens under ephemeral_5m_input_tokens.
    usage = {
        "input_tokens": 3000,
        "output_tokens": 400,
        "input_token_details": {
            "cache_read": 0,
            "cache_creation": 0,
            "ephemeral_5m_input_tokens": 2000,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    expected = (1000 * 0.10 + 2000 * 0.125 + 400 * 0.50) / 1e6
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(expected)

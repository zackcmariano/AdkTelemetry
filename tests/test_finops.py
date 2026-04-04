import pytest

from adktelemetry.finops import clear_pricing_cache, estimate_interaction_cost_usd


@pytest.fixture(autouse=True)
def _clear_finops_cache():
    clear_pricing_cache()
    yield
    clear_pricing_cache()


def test_estimate_cost_gemini_25_flash():
    cost, mid = estimate_interaction_cost_usd(
        model_id="gemini-2.5-flash",
        prompt_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert mid == "gemini-2.5-flash"
    assert abs(cost - (0.3 + 2.5)) < 1e-6


def test_unknown_model_zero_cost():
    cost, mid = estimate_interaction_cost_usd(
        model_id="unknown-model-xyz",
        prompt_tokens=1000,
        output_tokens=1000,
    )
    assert mid == "unknown-model-xyz"
    assert cost == 0.0


def test_normalize_models_prefix():
    cost, mid = estimate_interaction_cost_usd(
        model_id="models/gemini-2.5-flash",
        prompt_tokens=0,
        output_tokens=0,
    )
    assert mid == "gemini-2.5-flash"
    assert cost == 0.0

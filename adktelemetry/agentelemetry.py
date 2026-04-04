"""
AdkTelemetry entrypoint: install hooks and expose the `/adktelemetry` dashboard.

The background telemetry collector does not participate in user-facing agent
turns; it observes ADK `Runner` events and aggregates per-session FinOps and
error signals. Optional future use of `modelkey` may power LLM-based log
analysis without exposing the secret via the HTTP API.
"""

from __future__ import annotations

import logging

from adktelemetry.config import TelemetryConfig, set_config
from adktelemetry.hooks import ensure_runner_patch
from adktelemetry.patch_cli import ensure_fast_api_patch

logger = logging.getLogger("adktelemetry")


def agentelemetry(
    *,
    modelkey: str,
    adkmodel: str = "gemini-2.5-flash",
    pricing_config_path: str | None = None,
) -> None:
    """
    Enable AdkTelemetry for the current process.

    Args:
        modelkey: Required. Gemini API key for the host application (stored in
            memory only; never served on `/adktelemetry` endpoints).
        adkmodel: Default Gemini model id used when an event has no
            `model_version` (FinOps fallback). Default: gemini-2.5-flash.
        pricing_config_path: Optional path to a YAML file with the same shape as
            `adktelemetry/gemini_pricing.yaml` for custom or updated rates.

    Call once at process startup (e.g. alongside your ADK app import) before
    `adk web` constructs the FastAPI app so the `get_fast_api_app` patch applies.
    """
    if not modelkey or not str(modelkey).strip():
        raise ValueError("agentelemetry(): modelkey is required and cannot be empty.")

    set_config(
        TelemetryConfig(
            adkmodel=(adkmodel or "gemini-2.5-flash").strip(),
            modelkey=str(modelkey).strip(),
            pricing_config_path=pricing_config_path,
        )
    )
    ensure_runner_patch()
    # Idempotent: often no-op for HTTP if `services.py` already called
    # `ensure_adk_web_server_patch()` before the FastAPI app was built.
    ensure_fast_api_patch()
    logger.info(
        "AdkTelemetry enabled (default model=%s). Dashboard: <port>/adktelemetry",
        adkmodel,
    )

"""Runtime configuration set by `agentelemetry()`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TelemetryConfig:
    adkmodel: str = "gemini-2.5-flash"
    modelkey: str = ""
    pricing_config_path: str | None = None


_CONFIG: TelemetryConfig | None = None


def set_config(cfg: TelemetryConfig) -> None:
    global _CONFIG
    _CONFIG = cfg


def get_config() -> TelemetryConfig | None:
    return _CONFIG

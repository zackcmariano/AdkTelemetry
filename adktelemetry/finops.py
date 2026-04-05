"""FinOps: load Gemini list prices and estimate USD cost from usage metadata."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_YAML = Path(__file__).resolve().parent / "gemini_pricing.yaml"

GEMINI_PRICING_DOC_URL = "https://ai.google.dev/gemini-api/docs/pricing?hl=pt-br"


def _catalog_updated_mm_yy(config_path: str | None) -> str:
    """Month/year (MM/YY) from YAML meta.last_sync_utc, e.g. 2026-04-02 -> 04/26."""
    p = Path(config_path) if config_path else _DEFAULT_YAML
    if not p.is_file():
        return "04/26"
    try:
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        return "04/26"
    meta = data.get("meta") if isinstance(data, dict) else None
    if not isinstance(meta, dict):
        return "04/26"
    raw = meta.get("last_sync_utc") or meta.get("last_updated")
    if not raw or not isinstance(raw, str):
        return "04/26"
    m = re.match(r"^(\d{4})-(\d{2})", raw.strip())
    if not m:
        return "04/26"
    year = int(m.group(1))
    month = int(m.group(2))
    return f"{month:02d}/{year % 100:02d}"


def _normalize_model_id(name: str | None) -> str | None:
    if not name:
        return None
    s = name.strip().lower()
    s = re.sub(r"^models/", "", s)
    return s


@lru_cache(maxsize=32)
def _load_table(path: str | None) -> dict[str, dict[str, float]]:
    p = Path(path) if path else _DEFAULT_YAML
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = (data.get("models") or {}) if isinstance(data, dict) else {}
    out: dict[str, dict[str, float]] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        key = _normalize_model_id(str(k))
        if not key:
            continue
        inp = v.get("input_per_million_usd")
        outp = v.get("output_per_million_usd")
        if inp is None or outp is None:
            continue
        out[key] = {
            "input_per_million_usd": float(inp),
            "output_per_million_usd": float(outp),
        }
    return out


def clear_pricing_cache() -> None:
    _load_table.cache_clear()


def estimate_interaction_cost_usd(
    *,
    model_id: str | None,
    prompt_tokens: int,
    output_tokens: int,
    config_path: str | None = None,
) -> tuple[float, str | None]:
    """
    Returns (estimated_usd, resolved_model_key_or_none).
    Uses config file rates per 1M tokens. Unknown models return 0.0 cost.
    """
    norm = _normalize_model_id(model_id)
    table = _load_table(config_path)
    if not norm or norm not in table:
        return 0.0, norm
    row = table[norm]
    cost = (prompt_tokens / 1_000_000.0) * row["input_per_million_usd"]
    cost += (output_tokens / 1_000_000.0) * row["output_per_million_usd"]
    return cost, norm


def usage_metadata_to_counts(usage: Any) -> tuple[int, int]:
    """Best-effort prompt/candidates token counts from google.genai usage object."""
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_token_count", None)
    candidates = getattr(usage, "candidates_token_count", None)
    total = getattr(usage, "total_token_count", None)
    p = int(prompt or 0)
    c = int(candidates or 0)
    if p == 0 and c == 0 and total:
        return int(total), 0
    return p, c


def list_known_models(config_path: str | None = None) -> list[str]:
    return sorted(_load_table(config_path).keys())


def pricing_catalog(config_path: str | None = None) -> dict[str, Any]:
    """
    FinOps rows for API/dashboard: USD per 10,000 tokens, derived from YAML rates per 1M tokens.
    """
    table = _load_table(config_path)
    models: list[dict[str, Any]] = []
    for mid in sorted(table.keys()):
        row = table[mid]
        inp_m = float(row["input_per_million_usd"])
        out_m = float(row["output_per_million_usd"])
        models.append(
            {
                "model_id": mid,
                "input_usd_per_10k": inp_m / 100.0,
                "output_usd_per_10k": out_m / 100.0,
            }
        )
    return {
        "models": models,
        "unit_label": "USD per 10,000 tokens (text; derived from catalog per-1M rates)",
        "catalog_updated": _catalog_updated_mm_yy(config_path),
        "pricing_doc_url": GEMINI_PRICING_DOC_URL,
    }

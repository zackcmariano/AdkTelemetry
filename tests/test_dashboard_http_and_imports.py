"""
Guarantee that `pip install adktelemetry` pulls everything needed for:
imports used by the dashboard, snapshot/stream APIs, hooks, and SSE wrapper.

These tests fail if a direct third-party dependency is missing from pyproject.toml.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from adktelemetry.server import register_routes
from adktelemetry.store import TelemetryStore


def _pyproject_dependency_lines() -> list[str]:
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    out: list[str] = []
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("]"):
                break
            m = re.search(r'"([^"]+)"', line)
            if m:
                out.append(m.group(1))
    return out


def _pypi_name(dep_line: str) -> str:
    m = re.match(r"^([a-zA-Z0-9_.-]+)", dep_line.strip())
    assert m, dep_line
    return m.group(1).lower().replace("_", "-")


# Every [project.dependencies] entry must map to an importable top-level module
# (or well-known namespace) used after install.
_PYPI_TO_IMPORT = {
    "google-adk": "google.adk",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "pyyaml": "yaml",
}


@pytest.mark.parametrize(
    "module",
    [
        "yaml",
        "fastapi",
        "starlette.responses",
        "google.adk.runners",
        "google.adk.events.event",
        "adktelemetry.config",
        "adktelemetry.finops",
        "adktelemetry.live_notify",
        "adktelemetry.store",
        "adktelemetry.server",
        "adktelemetry.sse_telemetry",
        "adktelemetry.hooks",
        "adktelemetry.patch_cli",
        "adktelemetry.agentelemetry",
    ],
)
def test_dashboard_stack_imports(module: str) -> None:
    importlib.import_module(module)


def test_pyproject_dependencies_are_importable() -> None:
    for line in _pyproject_dependency_lines():
        if line.strip().startswith("#"):
            continue
        name = _pypi_name(line)
        mod = _PYPI_TO_IMPORT.get(name)
        assert mod, f"Add mapping for pyproject dependency {name!r}"
        importlib.import_module(mod)


def test_register_routes_http_surface() -> None:
    TelemetryStore.reset_for_tests()
    app = FastAPI()
    register_routes(app)
    client = TestClient(app)

    r = client.get("/adktelemetry/")
    assert r.status_code == 200
    assert "AdkTelemetry" in r.text

    r = client.get("/adktelemetry/api/v1/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body
    assert "sessions" in body
    assert "model_distribution" in body
    assert "pricing_models" in body

    r = client.get("/adktelemetry/api/v1/pricing_catalog")
    assert r.status_code == 200
    pc = r.json()
    assert "models" in pc
    assert "catalog_updated" in pc

    r = client.get("/adktelemetry/api/v1/error_breakdown")
    assert r.status_code == 200
    assert "total" in r.json()

    r = client.get(
        "/adktelemetry/api/v1/session_detail",
        params={"user_id": "u", "session_id": "missing"},
    )
    assert r.status_code == 404


def test_stream_route_registered() -> None:
    """Long-lived SSE is hard to exercise under TestClient without blocking; ensure route exists."""
    app = FastAPI()
    register_routes(app)
    paths = [
        r.path
        for r in app.routes
        if isinstance(r, APIRoute)
    ]
    assert "/adktelemetry/api/v1/stream" in paths

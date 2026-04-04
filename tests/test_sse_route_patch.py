"""Ensure /run_sse wrapping updates FastAPI dependant.call (wrapper actually runs)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from google.adk.events.event import Event
from google.genai import types
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from adktelemetry.sse_telemetry import patch_run_sse_route
from adktelemetry.store import TelemetryStore


class RunAgentRequest(BaseModel):
    app_name: str
    user_id: str
    session_id: str
    streaming: bool = False


async def fake_run_sse(req: RunAgentRequest) -> StreamingResponse:
    async def gen():
        err = Exception("404 NOT_FOUND. {'error': {'code': 404}}")
        error_event = Event(
            author="system",
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"Error: {err}")],
            ),
        )
        line = error_event.model_dump_json(by_alias=True, exclude_none=True)
        yield f"data: {line}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def test_patch_updates_dependant_call():
    app = FastAPI()
    app.add_api_route("/run_sse", fake_run_sse, methods=["POST"])
    patch_run_sse_route(app)
    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/run_sse")
    assert route.endpoint is route.dependant.call
    assert getattr(route.endpoint, "_adktelemetry_sse_wrapped", False)


def test_client_consuming_stream_records_telemetry_error():
    TelemetryStore.reset_for_tests()
    app = FastAPI()
    app.add_api_route("/run_sse", fake_run_sse, methods=["POST"])
    patch_run_sse_route(app)
    client = TestClient(app)
    r = client.post(
        "/run_sse",
        json={"app_name": "app", "user_id": "user", "session_id": "sess-sse-1", "streaming": False},
    )
    assert r.status_code == 200
    _ = r.content
    snap = TelemetryStore.instance().snapshot()
    assert snap["totals"]["errors"] == 1
    assert snap["sessions"][0]["session_id"] == "sess-sse-1"

"""Capture ADK Dev UI synthetic errors from `/run_sse` (not emitted via Runner)."""

from __future__ import annotations

import functools
import json
import logging
from typing import Any

from starlette.responses import StreamingResponse

logger = logging.getLogger("adktelemetry.sse")

_SSE_BUFFER_MAX = 256 * 1024


def _process_sse_block(block: str, *, user_id: str, session_id: str) -> None:
    for line in block.split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        author = data.get("author")
        if author != "system":
            continue
        content = data.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts") or []
        texts: list[str] = []
        for p in parts:
            if isinstance(p, dict) and p.get("text"):
                texts.append(str(p["text"]))
        combined = "\n".join(texts).strip()
        if not combined.startswith("Error:"):
            continue
        try:
            from google.adk.events.event import Event

            evt = Event.model_validate(data)
        except Exception:
            logger.debug("SSE telemetry: could not validate system error event", exc_info=True)
            continue
        try:
            from adktelemetry.config import get_config
            from adktelemetry.store import TelemetryStore, event_to_record

            cfg = get_config()
            rec = event_to_record(evt)
            TelemetryStore.instance().record_event(
                user_id=user_id,
                session_id=session_id,
                record=rec,
                default_model=cfg.adkmodel if cfg else None,
                pricing_config_path=cfg.pricing_config_path if cfg else None,
            )
        except Exception:
            logger.exception("AdkTelemetry: failed to record SSE system error")


def wrap_streaming_response_with_sse_telemetry(
    resp: Any,
    *,
    user_id: str,
    session_id: str,
) -> Any:
    """If `resp` is SSE from `/run_sse`, tee chunks and record synthetic system Error events."""
    if not isinstance(resp, StreamingResponse):
        return resp

    orig_it = resp.body_iterator

    async def wrapped_it():
        buffer = ""
        async for chunk in orig_it:
            if isinstance(chunk, memoryview):
                chunk = chunk.tobytes()
            text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
            buffer += text
            if len(buffer) > _SSE_BUFFER_MAX:
                buffer = buffer[-_SSE_BUFFER_MAX:]
            while True:
                sep = buffer.find("\n\n")
                if sep == -1:
                    break
                block = buffer[:sep]
                buffer = buffer[sep + 2 :]
                _process_sse_block(block, user_id=user_id, session_id=session_id)
            yield chunk

    return StreamingResponse(
        wrapped_it(),
        status_code=resp.status_code,
        headers=resp.headers,
        media_type=resp.media_type,
        background=resp.background,
    )


def _iter_api_routes(app: Any):
    """Walk FastAPI routes including mounts (defensive for prefixed sub-apps)."""
    try:
        from fastapi.routing import APIRoute
        from starlette.routing import Mount
    except ImportError:
        return

    stack = list(getattr(app, "routes", []) or [])
    while stack:
        route = stack.pop()
        if isinstance(route, APIRoute):
            yield route
        elif isinstance(route, Mount):
            stack.extend(getattr(route, "routes", []) or [])


def patch_run_sse_route(app: Any) -> None:
    """Wrap POST `/run_sse` so synthetic `author=system` error events update TelemetryStore.

    FastAPI binds the ASGI handler to `route.dependant.call` at route construction time.
    Replacing only `route.endpoint` leaves the old callable in `dependant.call`, so the
    wrapper would never run; we must update `dependant.call` as well.
    """
    try:
        from fastapi.routing import APIRoute
    except ImportError:
        return

    for route in _iter_api_routes(app):
        if not isinstance(route, APIRoute):
            continue
        path = (route.path or "").rstrip("/") or route.path
        if path != "/run_sse":
            continue
        methods = route.methods or set()
        if "POST" not in methods:
            continue
        if getattr(route.endpoint, "_adktelemetry_sse_wrapped", False):
            return
        orig = route.endpoint

        @functools.wraps(orig)
        async def wrapped(req: Any):
            out = await orig(req)
            return wrap_streaming_response_with_sse_telemetry(
                out,
                user_id=req.user_id,
                session_id=req.session_id,
            )

        wrapped._adktelemetry_sse_wrapped = True  # type: ignore[attr-defined]
        route.endpoint = wrapped
        route.dependant.call = wrapped  # type: ignore[union-attr]
        logger.info("AdkTelemetry: /run_sse wrapped for SSE error telemetry")
        return
    logger.warning(
        "AdkTelemetry: POST /run_sse not found — SSE synthetic errors will not appear in telemetry"
    )

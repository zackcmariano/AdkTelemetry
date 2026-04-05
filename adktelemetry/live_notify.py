"""
Push dashboard refresh signals when telemetry changes (Runner + SSE error path).

Uses the asyncio event loop registered by the first live stream connection.
Debounces bursts of record_event calls so one SSE tick coalesces rapid session updates.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

_subscribers: set[asyncio.Queue[Any]] = set()
_sub_lock = threading.Lock()
_loop_ref: asyncio.AbstractEventLoop | None = None
_timer_lock = threading.Lock()
_timer: threading.Timer | None = None

# Trailing debounce: merge many events in one LLM turn into a single push.
_DEBOUNCE_SEC = 0.08


def register_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remember the server loop (typically uvicorn's main loop)."""
    global _loop_ref
    _loop_ref = loop


def subscribe() -> asyncio.Queue[Any]:
    q: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
    with _sub_lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue[Any]) -> None:
    with _sub_lock:
        _subscribers.discard(q)


def _broadcast() -> None:
    loop = _loop_ref
    if loop is None:
        return

    def _do() -> None:
        with _sub_lock:
            targets = list(_subscribers)
        for q in targets:
            try:
                try:
                    while True:
                        q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(1)
            except Exception:
                with _sub_lock:
                    _subscribers.discard(q)

    try:
        loop.call_soon_threadsafe(_do)
    except RuntimeError:
        pass


def notify_telemetry_changed() -> None:
    """Called from TelemetryStore after each recorded event (any thread)."""
    if _loop_ref is None:
        return

    def _fire() -> None:
        global _timer
        with _timer_lock:
            _timer = None
        _broadcast()

    with _timer_lock:
        global _timer
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(_DEBOUNCE_SEC, _fire)
        _timer.daemon = True
        _timer.start()


def reset_for_tests() -> None:
    """Clear subscribers and pending debounce (unit tests)."""
    global _timer, _loop_ref
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    with _sub_lock:
        _subscribers.clear()
    _loop_ref = None

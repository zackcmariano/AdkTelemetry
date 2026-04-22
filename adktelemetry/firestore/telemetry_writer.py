"""
Async, queue-backed mirror of AdkTelemetry records into Firestore.

Design goals:
    * Never block the ADK runner loop on a Firestore round-trip.
    * Drop-oldest backpressure so a slow network cannot exhaust memory.
    * Survive transient Firestore errors without crashing the agent turn.

The writer is started lazily on the first enqueue (inside the running asyncio
loop) and lives for the process lifetime. One writer per process; consumers
(e.g. the runner hook) push records via `enqueue_record(...)` and move on.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from adktelemetry.firestore.config import get_firestore_config
from adktelemetry.firestore.session_service import FirestoreSessionService

logger = logging.getLogger("adktelemetry.firestore.writer")

_MAX_QUEUE = 2000
_queue: deque[dict[str, Any]] = deque()
_worker_task: asyncio.Task | None = None
_shutdown = False


def _get_or_spawn_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. sync CLI path); the enqueue is a no-op by design.
        return
    _worker_task = loop.create_task(_worker(), name="adktelemetry-firestore-writer")


def enqueue_record(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    record: dict[str, Any],
) -> None:
    """Queue one telemetry record for asynchronous write. Never raises."""
    cfg = get_firestore_config()
    if cfg is None or not cfg.mirror_telemetry:
        return
    if not (app_name and user_id and session_id):
        return
    try:
        if len(_queue) >= _MAX_QUEUE:
            _queue.popleft()  # drop-oldest backpressure
        _queue.append(
            {
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "record": dict(record),
            }
        )
        _get_or_spawn_worker()
    except Exception:
        logger.exception("AdkTelemetry[firestore]: enqueue_record failed")


async def _worker() -> None:
    logger.info("AdkTelemetry[firestore]: telemetry writer started")
    service = FirestoreSessionService()
    try:
        while not _shutdown:
            if not _queue:
                await asyncio.sleep(0.25)
                continue
            item = _queue.popleft()
            try:
                await service.record_telemetry(
                    app_name=item["app_name"],
                    user_id=item["user_id"],
                    session_id=item["session_id"],
                    record=item["record"],
                )
            except Exception:
                logger.exception(
                    "AdkTelemetry[firestore]: writer flush failed session=%s",
                    item.get("session_id"),
                )
                # Light backoff to avoid tight error loops.
                await asyncio.sleep(0.5)
    finally:
        logger.info("AdkTelemetry[firestore]: telemetry writer stopped")


def shutdown() -> None:
    global _shutdown
    _shutdown = True

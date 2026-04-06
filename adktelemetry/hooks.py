"""Patch Google ADK `Runner.run_async` to capture events into `TelemetryStore`."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any, Optional

logger = logging.getLogger("adktelemetry.hooks")

_orig_run_async: Any = None
_installed = False


def _install() -> None:
    global _orig_run_async, _installed
    if _installed:
        return
    from google.adk.runners import Runner

    _orig_run_async = Runner.run_async

    async def _wrapped(
        self: Any,
        *,
        user_id: str,
        session_id: str,
        invocation_id: Optional[str] = None,
        new_message: Any = None,
        state_delta: Optional[dict[str, Any]] = None,
        run_config: Any = None,
    ) -> AsyncGenerator[Any, None]:
        from adktelemetry.config import get_config
        from adktelemetry.store import (
            TelemetryStore,
            event_to_record,
            runner_failure_to_record,
        )

        cfg = get_config()
        default_model = cfg.adkmodel if cfg else None
        pricing_path = cfg.pricing_config_path if cfg else None
        store = TelemetryStore.instance()

        try:
            async for event in _orig_run_async(
                self,
                user_id=user_id,
                session_id=session_id,
                invocation_id=invocation_id,
                new_message=new_message,
                state_delta=state_delta,
                run_config=run_config,
            ):
                try:
                    rec = event_to_record(event)
                    store.record_event(
                        user_id=user_id,
                        session_id=session_id,
                        record=rec,
                        default_model=default_model,
                        pricing_config_path=pricing_path,
                    )
                except Exception:
                    logger.exception("AdkTelemetry: failed to record event")
                yield event
        except Exception as e:
            # LLM/API failures often abort the async generator before any error Event is yielded.
            # ADK web server then emits data: {"error": "..."} on the wire; record here so the
            # dashboard sees the failure without relying on that SSE shape (and we avoid double-counting).
            try:
                store.record_event(
                    user_id=user_id,
                    session_id=session_id,
                    record=runner_failure_to_record(e),
                    default_model=default_model,
                    pricing_config_path=pricing_path,
                )
            except Exception:
                logger.exception("AdkTelemetry: failed to record runner failure")
            raise

    Runner.run_async = _wrapped  # type: ignore[method-assign]
    _installed = True
    logger.info("AdkTelemetry: Runner.run_async telemetry hook installed")


def ensure_runner_patch() -> None:
    _install()

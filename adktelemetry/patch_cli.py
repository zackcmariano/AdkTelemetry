"""Patch ADK HTTP stack so `/adktelemetry` is registered on the dev server."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("adktelemetry.patch_cli")

_orig_get_app: Any = None
_orig_adk_ws_get_app: Any = None
_orig_adk_ws_init: Any = None
_module_patch_installed = False
_web_server_patch_installed = False
_firestore_session_patch_installed = False


def ensure_adk_web_server_patch() -> None:
    """Patch `AdkWebServer.get_fast_api_app` (runs from `services.py` before the app is built)."""
    global _orig_adk_ws_get_app, _web_server_patch_installed
    if _web_server_patch_installed:
        return
    from google.adk.cli.adk_web_server import AdkWebServer

    _orig_adk_ws_get_app = AdkWebServer.get_fast_api_app

    def _wrapped_ws(self: Any, *args: Any, **kwargs: Any):
        app = _orig_adk_ws_get_app(self, *args, **kwargs)
        try:
            from adktelemetry.server import register_routes
            from adktelemetry.sse_telemetry import patch_run_sse_route

            register_routes(app)
            patch_run_sse_route(app)
        except Exception:
            logger.exception("AdkTelemetry: could not register /adktelemetry routes")
        return app

    AdkWebServer.get_fast_api_app = _wrapped_ws  # type: ignore[method-assign]
    _web_server_patch_installed = True
    logger.info("AdkTelemetry: AdkWebServer.get_fast_api_app patch installed (/adktelemetry)")


def _install_module_and_cli_patch() -> None:
    global _orig_get_app, _module_patch_installed
    if _module_patch_installed:
        return
    import google.adk.cli.fast_api as fast_api_mod

    _orig_get_app = fast_api_mod.get_fast_api_app

    def _wrapped(*args: Any, **kwargs: Any):
        app = _orig_get_app(*args, **kwargs)
        try:
            from adktelemetry.server import register_routes
            from adktelemetry.sse_telemetry import patch_run_sse_route

            register_routes(app)
            patch_run_sse_route(app)
        except Exception:
            logger.exception("AdkTelemetry: could not register /adktelemetry routes")
        return app

    fast_api_mod.get_fast_api_app = _wrapped  # type: ignore[assignment]
    try:
        import google.adk.cli.cli_tools_click as click_mod

        click_mod.get_fast_api_app = _wrapped  # type: ignore[attr-defined]
    except Exception:
        logger.debug("cli_tools_click not patched (module load order)", exc_info=True)

    _module_patch_installed = True
    logger.info("AdkTelemetry: get_fast_api_app module patch installed (/adktelemetry)")


def ensure_fast_api_patch() -> None:
    """Patch module-level `get_fast_api_app` + CLI binding (when called early enough)."""
    ensure_adk_web_server_patch()
    _install_module_and_cli_patch()


def ensure_firestore_session_patch() -> None:
    """
    Swap `AdkWebServer.session_service` for a `FirestoreSessionService` at boot.

    `AdkWebServer.__init__` receives a `session_service` (usually an
    `InMemorySessionService` built from `--session_service_uri`). We let the
    original constructor run, then overwrite the attribute so every fastapi
    route served by the web server reads/writes through Firestore.
    """
    global _orig_adk_ws_init, _firestore_session_patch_installed
    if _firestore_session_patch_installed:
        return
    from google.adk.cli.adk_web_server import AdkWebServer

    _orig_adk_ws_init = AdkWebServer.__init__

    def _wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
        _orig_adk_ws_init(self, *args, **kwargs)
        try:
            from adktelemetry.firestore.config import get_firestore_config
            from adktelemetry.firestore.session_service import FirestoreSessionService

            if get_firestore_config() is not None:
                previous = getattr(self, "session_service", None)
                self.session_service = FirestoreSessionService()
                logger.info(
                    "AdkTelemetry[firestore]: session_service swapped (%s -> FirestoreSessionService)",
                    type(previous).__name__ if previous is not None else "None",
                )
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: failed to install FirestoreSessionService; "
                "falling back to the service provided to AdkWebServer."
            )

    AdkWebServer.__init__ = _wrapped_init  # type: ignore[method-assign]
    _firestore_session_patch_installed = True
    logger.info("AdkTelemetry[firestore]: AdkWebServer.__init__ patch installed")

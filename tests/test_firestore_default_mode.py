"""
Default mode guarantees (no `agentfirestore()` call).

When the developer only calls `agentelemetry()`, the library MUST behave
identically to the pre-Firestore release:
    * `get_firestore_config()` stays `None`.
    * No Firestore client (sync or async) gets instantiated.
    * The AdkWebServer session-service swap patch is NOT installed.
    * The runner telemetry mirror is a no-op (never calls into firestore.*).
    * TelemetryStore keeps feeding the dashboard just like before.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _isolate_firestore_state():
    # Fresh module state per test: avoids cross-test leakage of module-level
    # singletons (config slot, client cache).
    from adktelemetry.firestore import client as fs_client
    from adktelemetry.firestore import config as fs_config

    fs_config.set_firestore_config(None)  # type: ignore[arg-type]
    fs_client.reset_clients_for_tests()
    yield
    fs_config.set_firestore_config(None)  # type: ignore[arg-type]
    fs_client.reset_clients_for_tests()


def test_fresh_import_has_no_firestore_config():
    from adktelemetry.firestore.config import get_firestore_config

    assert get_firestore_config() is None


def test_agentelemetry_alone_does_not_configure_firestore(monkeypatch):
    # agentelemetry() should NOT wire Firestore even by accident.
    from adktelemetry.agentelemetry import agentelemetry
    from adktelemetry.firestore.config import get_firestore_config

    agentelemetry(modelkey="fake-key", adkmodel="gemini-2.5-flash")
    assert get_firestore_config() is None


def test_mirror_is_noop_without_config():
    # Direct unit test: the runner hook helper must short-circuit.
    from adktelemetry.hooks import _mirror_to_firestore

    # Poison: if it tried to do anything, it would have to import and touch
    # firestore internals. The assertion here is simply "no exception".
    _mirror_to_firestore("app", "user", "session-x", {"event_type": "adk"})


def test_enqueue_record_is_noop_without_config():
    # telemetry_writer must drop enqueues when firestore is disabled.
    from adktelemetry.firestore import telemetry_writer

    telemetry_writer.enqueue_record(
        app_name="app",
        user_id="user",
        session_id="session-x",
        record={"event_type": "adk"},
    )
    # Queue stays empty because config is None (drop at the gate, not post-enqueue).
    assert len(telemetry_writer._queue) == 0


def test_client_factory_raises_when_not_configured():
    from adktelemetry.firestore.client import FirestoreNotConfiguredError, get_async_client

    with pytest.raises(FirestoreNotConfiguredError):
        get_async_client()


def test_firestore_session_patch_preserves_session_service_without_config(monkeypatch):
    """
    `ensure_firestore_session_patch` installs a wrapper around
    `AdkWebServer.__init__`. With no FirestoreConfig, the wrapper must NOT
    touch `self.session_service` (i.e. the one provided by the caller wins).
    """
    from adktelemetry import patch_cli
    from adktelemetry.firestore.config import get_firestore_config
    from google.adk.cli.adk_web_server import AdkWebServer

    sentinel_service = object()

    # Replace the captured original with a minimal fake that only sets the
    # attributes our wrapper reads. Patch installation is idempotent, so we
    # simulate a fresh install against this fake by saving+restoring state.
    original_orig = patch_cli._orig_adk_ws_init
    original_installed_flag = patch_cli._firestore_session_patch_installed
    original_class_init = AdkWebServer.__init__

    def fake_init(self, session_service):
        self.session_service = session_service

    try:
        patch_cli._orig_adk_ws_init = None  # type: ignore[assignment]
        patch_cli._firestore_session_patch_installed = False
        AdkWebServer.__init__ = fake_init  # type: ignore[method-assign]
        patch_cli.ensure_firestore_session_patch()

        obj = AdkWebServer.__new__(AdkWebServer)
        AdkWebServer.__init__(obj, sentinel_service)

        assert get_firestore_config() is None
        assert obj.session_service is sentinel_service, (
            "Without agentfirestore(), the wrapper must not replace session_service."
        )
    finally:
        AdkWebServer.__init__ = original_class_init  # type: ignore[method-assign]
        patch_cli._orig_adk_ws_init = original_orig
        patch_cli._firestore_session_patch_installed = original_installed_flag

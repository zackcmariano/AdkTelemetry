"""
Firestore mode guarantees (with `agentfirestore()`), no real GCP needed.

We install a `FirestoreConfig` by hand (skipping `agentfirestore()`'s client
build) and verify that:
    * `_mirror_to_firestore` actually enqueues into the async writer queue.
    * `enqueue_record` honours `mirror_telemetry=False`.
    * The AdkWebServer __init__ wrapper swaps `session_service` when the
      config is present, without relying on any real Firestore call.
"""

from __future__ import annotations

import pytest

from adktelemetry.firestore.config import FirestoreConfig, set_firestore_config


@pytest.fixture(autouse=True)
def _isolate_firestore_state():
    from adktelemetry.firestore import client as fs_client
    from adktelemetry.firestore import config as fs_config
    from adktelemetry.firestore import telemetry_writer as fs_writer

    fs_config.set_firestore_config(None)  # type: ignore[arg-type]
    fs_writer._queue.clear()
    fs_client.reset_clients_for_tests()
    yield
    fs_config.set_firestore_config(None)  # type: ignore[arg-type]
    fs_writer._queue.clear()
    fs_client.reset_clients_for_tests()


def _install_fake_config(mirror: bool = True) -> FirestoreConfig:
    cfg = FirestoreConfig(
        project_id="unit-test-project",
        database="(default)",
        root_collection="adk_agents",
        credentials_path=None,
        credentials_info=None,
        mirror_telemetry=mirror,
    )
    set_firestore_config(cfg)
    return cfg


def test_mirror_enqueues_when_configured():
    from adktelemetry.firestore import telemetry_writer
    from adktelemetry.hooks import _mirror_to_firestore

    _install_fake_config(mirror=True)

    _mirror_to_firestore(
        "app",
        "user",
        "session-abc",
        {"event_type": "adk", "input_tokens": 10},
    )

    # One item queued; worker spawn is attempted but safely skipped because
    # there is no running event loop in a sync test (by design).
    assert len(telemetry_writer._queue) == 1
    item = telemetry_writer._queue[0]
    assert item["app_name"] == "app"
    assert item["session_id"] == "session-abc"
    assert item["record"]["input_tokens"] == 10


def test_mirror_respects_mirror_telemetry_flag():
    from adktelemetry.firestore import telemetry_writer
    from adktelemetry.hooks import _mirror_to_firestore

    _install_fake_config(mirror=False)
    _mirror_to_firestore("app", "user", "session-abc", {"event_type": "adk"})

    assert len(telemetry_writer._queue) == 0


def test_mirror_drops_when_user_or_session_missing():
    """
    Contract:
        * Empty `user_id` or `session_id` -> drop (no session to bind the record to).
        * Empty `app_name` -> fallback to "default" (Runner may not populate it).
    """
    from adktelemetry.firestore import telemetry_writer
    from adktelemetry.hooks import _mirror_to_firestore

    _install_fake_config(mirror=True)
    _mirror_to_firestore("app", "", "session-abc", {"event_type": "adk"})
    _mirror_to_firestore("app", "user", "", {"event_type": "adk"})
    assert len(telemetry_writer._queue) == 0

    _mirror_to_firestore("", "user", "session-abc", {"event_type": "adk"})
    assert len(telemetry_writer._queue) == 1
    assert telemetry_writer._queue[0]["app_name"] == "default"


def test_mirror_backpressure_drops_oldest(monkeypatch):
    from adktelemetry.firestore import telemetry_writer

    _install_fake_config(mirror=True)
    # Shrink the cap to exercise backpressure quickly.
    monkeypatch.setattr(telemetry_writer, "_MAX_QUEUE", 3)

    for i in range(5):
        telemetry_writer.enqueue_record(
            app_name="app",
            user_id="user",
            session_id=f"s{i}",
            record={"event_type": "adk"},
        )

    assert len(telemetry_writer._queue) == 3
    # Drop-oldest: the 2 oldest (s0, s1) should be gone.
    ids = [item["session_id"] for item in telemetry_writer._queue]
    assert ids == ["s2", "s3", "s4"]


def test_adkwebserver_init_wrapper_swaps_session_service_when_configured(monkeypatch):
    """With Firestore configured, the __init__ wrapper must install a
    FirestoreSessionService in place of the one passed by the CLI."""
    from adktelemetry import patch_cli
    from adktelemetry.firestore.session_service import FirestoreSessionService
    from google.adk.cli.adk_web_server import AdkWebServer

    _install_fake_config(mirror=True)

    # Replace our service impl with a lightweight stand-in so we do not talk
    # to the network. The wrapper only imports the class; it does not call
    # its Firestore-touching methods.
    class _FakeService(FirestoreSessionService):
        def __init__(self):  # noqa: D401 - bypass real __init__
            pass

    monkeypatch.setattr(
        "adktelemetry.patch_cli.FirestoreSessionService",
        _FakeService,
        raising=False,
    )

    sentinel_service = object()
    original_orig = patch_cli._orig_adk_ws_init
    original_installed = patch_cli._firestore_session_patch_installed
    original_class_init = AdkWebServer.__init__

    def fake_init(self, session_service):
        self.session_service = session_service

    try:
        patch_cli._orig_adk_ws_init = None  # type: ignore[assignment]
        patch_cli._firestore_session_patch_installed = False
        AdkWebServer.__init__ = fake_init  # type: ignore[method-assign]
        patch_cli.ensure_firestore_session_patch()

        # Re-apply the monkeypatch AFTER ensure_* resolved the import so the
        # wrapper's late import picks our fake class.
        import adktelemetry.firestore.session_service as fs_ss

        monkeypatch.setattr(fs_ss, "FirestoreSessionService", _FakeService)

        obj = AdkWebServer.__new__(AdkWebServer)
        AdkWebServer.__init__(obj, sentinel_service)

        assert isinstance(obj.session_service, _FakeService), (
            f"Expected FirestoreSessionService swap, got {type(obj.session_service).__name__}"
        )
        assert obj.session_service is not sentinel_service
    finally:
        AdkWebServer.__init__ = original_class_init  # type: ignore[method-assign]
        patch_cli._orig_adk_ws_init = original_orig
        patch_cli._firestore_session_patch_installed = original_installed

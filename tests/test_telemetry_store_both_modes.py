"""
The AdkTelemetry dashboard is fed by the in-memory `TelemetryStore`. Both
modes (default + Firestore) must keep the store intact: the Firestore mirror
is *additive*, never a replacement. This test fixes that contract.
"""

from __future__ import annotations

import pytest

from adktelemetry.firestore.config import FirestoreConfig, set_firestore_config
from adktelemetry.store import TelemetryStore


@pytest.fixture(autouse=True)
def _reset_state():
    from adktelemetry.firestore import telemetry_writer

    TelemetryStore.reset_for_tests()
    set_firestore_config(None)  # type: ignore[arg-type]
    telemetry_writer._queue.clear()
    yield
    TelemetryStore.reset_for_tests()
    set_firestore_config(None)  # type: ignore[arg-type]
    telemetry_writer._queue.clear()


def _sample_record(session_id: str) -> dict:
    return {
        "event_type": "adk",
        "author": "especialista",
        "model_version": "gemini-2.5-flash",
        "input_tokens": 100,
        "output_tokens": 50,
        "error_code": None,
        "error_message": None,
    }


def test_store_feeds_dashboard_in_default_mode():
    store = TelemetryStore.instance()
    store.record_event(
        user_id="user",
        session_id="sess-default-1",
        record=_sample_record("sess-default-1"),
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    snap = store.snapshot()
    assert snap["totals"]["events"] == 1
    assert snap["sessions"][0]["session_id"] == "sess-default-1"
    assert snap["totals"]["errors"] == 0


def test_store_feeds_dashboard_in_firestore_mode():
    # Activate Firestore config (no real client is touched in this test).
    set_firestore_config(
        FirestoreConfig(
            project_id="unit-test-project",
            database="(default)",
            mirror_telemetry=True,
        )
    )

    store = TelemetryStore.instance()
    store.record_event(
        user_id="user",
        session_id="sess-firestore-1",
        record=_sample_record("sess-firestore-1"),
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    # TelemetryStore still carries the same data -> dashboard is unchanged.
    snap = store.snapshot()
    assert snap["totals"]["events"] == 1
    assert snap["sessions"][0]["session_id"] == "sess-firestore-1"


def test_firestore_mirror_does_not_steal_from_store():
    """
    Simulates the hook path end-to-end (without running an actual Runner):
    record into the store AND invoke the mirror helper. Both sinks must
    reflect the event.
    """
    from adktelemetry.firestore import telemetry_writer
    from adktelemetry.hooks import _mirror_to_firestore

    set_firestore_config(
        FirestoreConfig(
            project_id="unit-test-project",
            database="(default)",
            mirror_telemetry=True,
        )
    )

    rec = _sample_record("sess-mirror-1")
    store = TelemetryStore.instance()
    store.record_event(
        user_id="user",
        session_id="sess-mirror-1",
        record=rec,
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    _mirror_to_firestore("app", "user", "sess-mirror-1", rec)

    # Dashboard source (in-memory) still counts the event.
    assert store.snapshot()["totals"]["events"] == 1
    # Firestore writer queue accepted the mirror (real upload happens async).
    assert len(telemetry_writer._queue) == 1
    assert telemetry_writer._queue[0]["session_id"] == "sess-mirror-1"

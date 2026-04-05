"""Failures inside Runner.run_async (no yielded error Event) must still hit TelemetryStore."""

from __future__ import annotations

from adktelemetry.store import (
    TelemetryStore,
    fatal_error_message_to_record,
    runner_failure_to_record,
)


def test_fatal_error_message_matches_gemini_client_error_shape() -> None:
    msg = (
        "404 NOT_FOUND. {'error': {'code': 404, 'message': "
        "'models/gemini-3.1-flash-live-preview is not found', 'status': 'NOT_FOUND'}}"
    )
    rec = fatal_error_message_to_record(msg)
    assert rec["error_code"] == "NOT_FOUND"
    assert "404" in (rec["error_message"] or "")


def test_runner_failure_to_record_from_exception() -> None:
    exc = RuntimeError(
        "404 NOT_FOUND. {'error': {'code': 404, 'message': 'model not found', 'status': 'NOT_FOUND'}}"
    )
    rec = runner_failure_to_record(exc)
    assert rec["error_code"] == "NOT_FOUND"


def test_record_runner_failure_increments_errors() -> None:
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    rec = fatal_error_message_to_record(
        "404 NOT_FOUND. {'error': {'code': 404, 'message': 'x', 'status': 'NOT_FOUND'}}"
    )
    store.record_event(
        user_id="user",
        session_id="sess-runner-fail",
        record=rec,
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    snap = store.snapshot()
    assert snap["totals"]["errors"] == 1
    assert snap["sessions"][0]["session_id"] == "sess-runner-fail"
    assert snap["sessions"][0]["error_count"] == 1

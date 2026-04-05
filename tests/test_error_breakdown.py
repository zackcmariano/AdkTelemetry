import time

from adktelemetry.store import (
    TelemetryStore,
    short_error_label_for_dashboard,
)


def test_short_error_label_from_error_line():
    e = {
        "error_code": "NOT_FOUND",
        "error_message": "Error: 404 NOT_FOUND. {'error': {'code': 404}}",
    }
    assert short_error_label_for_dashboard(e) == "Error: 404 NOT_FOUND"


def test_short_error_label_leading_status():
    e = {"error_code": None, "error_message": "503 UNAVAILABLE upstream"}
    assert short_error_label_for_dashboard(e) == "Error: 503 UNAVAILABLE"


def test_short_error_label_from_code_only():
    e = {"error_code": "RESOURCE_EXHAUSTED", "error_message": ""}
    assert short_error_label_for_dashboard(e) == "Error: RESOURCE_EXHAUSTED"


def test_error_breakdown_counts_by_label():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    t0 = time.time()

    def rec(msg: str, code: str | None = "NOT_FOUND"):
        return {
            "timestamp": t0,
            "author": "system",
            "error_code": code,
            "error_message": msg,
            "usage": {"prompt_token_count": 0, "candidates_token_count": 0},
        }

    for _ in range(2):
        store.record_event(
            user_id="u",
            session_id="s1",
            record=rec("Error: 404 NOT_FOUND. x"),
            default_model=None,
            pricing_config_path=None,
        )
    store.record_event(
        user_id="u",
        session_id="s2",
        record=rec("Error: 503 UNAVAILABLE. y", code="UNAVAILABLE"),
        default_model=None,
        pricing_config_path=None,
    )

    bd = store.error_breakdown(t0 - 60, t0 + 60)
    assert bd["total"] == 3
    assert bd["top"]["label"] == "Error: 404 NOT_FOUND"
    assert bd["top"]["count"] == 2
    assert bd["top"]["percent"] > 66.0
    labels = {s["label"]: s["count"] for s in bd["slices"]}
    assert labels["Error: 404 NOT_FOUND"] == 2
    assert labels["Error: 503 UNAVAILABLE"] == 1
    assert bd["top"]["full_error_log"] == "Error: 404 NOT_FOUND. x"


def test_error_breakdown_empty_window():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    assert store.error_breakdown(time.time(), time.time() + 10) == {
        "total": 0,
        "slices": [],
        "top": None,
    }

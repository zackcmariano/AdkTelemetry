import time

from adktelemetry.store import TelemetryStore


def test_snapshot_filtered_empty():
    TelemetryStore.reset_for_tests()
    now = time.time()
    snap = TelemetryStore.instance().snapshot_filtered(
        now - 3600,
        now,
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    assert snap["totals"]["sessions"] == 0
    assert snap["totals"]["events"] == 0
    assert snap["totals"]["total_input_tokens"] == 0
    assert snap["totals"]["total_output_tokens"] == 0
    assert snap["totals"]["total_cost_usd"] == 0
    assert snap["totals"]["last_interaction_ts"] is None
    assert snap["activity_timeline"]["bucket_count"] == 24
    assert sum(snap["activity_timeline"]["counts"]) == 0
    assert snap["sessions"] == []


def test_snapshot_filtered_counts_events_in_window():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    t0 = 1_700_000_000.0
    t1 = t0 + 60
    t2 = t0 + 3600

    def rec(ts, model="gemini-2.5-flash"):
        return {
            "timestamp": ts,
            "model_version": model,
            "usage": {"prompt_token_count": 100, "candidates_token_count": 10},
            "error_code": None,
            "error_message": None,
        }

    store.record_event(
        user_id="u",
        session_id="s1",
        record=rec(t1),
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    store.record_event(
        user_id="u",
        session_id="s1",
        record=rec(t2),
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )

    snap = store.snapshot_filtered(
        t0 + 30,
        t0 + 120,
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    assert snap["totals"]["sessions"] == 1
    assert snap["totals"]["events"] == 1
    assert snap["totals"]["total_input_tokens"] == 100
    assert snap["totals"]["total_output_tokens"] == 10
    assert snap["totals"]["last_interaction_ts"] == t1
    assert snap["sessions"][0]["event_count"] == 1
    assert sum(snap["activity_timeline"]["counts"]) == 1

    snap_all = store.snapshot_filtered(
        t0,
        t2 + 10,
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    assert snap_all["totals"]["events"] == 2
    assert snap_all["totals"]["total_input_tokens"] == 200
    assert snap_all["totals"]["total_output_tokens"] == 20
    assert snap_all["totals"]["last_interaction_ts"] == t2
    assert float(snap_all["totals"]["total_cost_usd"]) >= 0
    assert sum(snap_all["activity_timeline"]["counts"]) == 2

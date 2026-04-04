"""Error detection when text only appears inside model_dump (Dev UI parity)."""

from adktelemetry.store import TelemetryStore, event_to_record


def test_event_to_record_finds_error_in_model_dump_when_content_empty():
    class FakeEvent:
        id = "evt-1"
        timestamp = 1.0
        author = "system"
        invocation_id = ""
        branch = None
        model_version = None
        partial = None
        error_code = None
        error_message = None
        usage_metadata = None
        content = None
        title = None

        def model_dump(self, mode="json", exclude_none=True):
            return {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Error: 404 NOT_FOUND. {'error': {'code': 404, "
                                "'message': 'model unavailable', 'status': 'NOT_FOUND'}}"
                            )
                        }
                    ]
                }
            }

    rec = event_to_record(FakeEvent())
    assert rec.get("error_code") == "NOT_FOUND"
    assert "404" in (rec.get("error_message") or "")
    assert rec.get("error_inferred_from_content") is True


def test_record_event_increments_session_errors():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    rec = {
        "id": "e1",
        "timestamp": 1.0,
        "author": "system",
        "invocation_id": "",
        "error_code": "NOT_FOUND",
        "error_message": "x",
    }
    store.record_event(
        user_id="u",
        session_id="s",
        record=rec,
        default_model=None,
        pricing_config_path=None,
    )
    snap = store.snapshot()
    assert snap["sessions"][0]["error_count"] == 1
    assert snap["totals"]["errors"] == 1


def test_benign_stop_does_not_count_without_message():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    store.record_event(
        user_id="u",
        session_id="s",
        record={
            "id": "e2",
            "timestamp": 2.0,
            "error_code": "STOP",
            "error_message": None,
        },
        default_model=None,
        pricing_config_path=None,
    )
    assert store.snapshot()["sessions"][0]["error_count"] == 0

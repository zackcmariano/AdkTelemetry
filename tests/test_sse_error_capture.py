import json

from adktelemetry.sse_telemetry import _process_sse_block
from adktelemetry.store import TelemetryStore


def test_process_sse_block_records_system_error():
    TelemetryStore.reset_for_tests()
    payload = {
        "author": "system",
        "content": {
            "role": "model",
            "parts": [
                {
                    "text": (
                        "Error: 404 NOT_FOUND. {'error': {'code': 404, "
                        "'message': 'model unavailable', 'status': 'NOT_FOUND'}}"
                    )
                }
            ],
        },
    }
    block = f"data: {json.dumps(payload)}\n"
    _process_sse_block(block, user_id="user", session_id="76726520-099c-4bbe-9896-8ac551850a78")
    snap = TelemetryStore.instance().snapshot()
    assert snap["totals"]["errors"] == 1
    assert snap["sessions"][0]["error_count"] == 1
    assert snap["sessions"][0]["session_id"] == "76726520-099c-4bbe-9896-8ac551850a78"


def test_process_sse_block_ignores_model_author():
    TelemetryStore.reset_for_tests()
    payload = {
        "author": "captain_america",
        "content": {"role": "model", "parts": [{"text": "Error: should not count"}]},
    }
    block = f"data: {json.dumps(payload)}\n"
    _process_sse_block(block, user_id="user", session_id="s1")
    snap = TelemetryStore.instance().snapshot()
    assert snap["totals"]["errors"] == 0

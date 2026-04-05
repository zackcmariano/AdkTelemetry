import time

from adktelemetry.store import (
    TelemetryStore,
    build_errors_brief,
    compile_session_summary_from_records,
)


def test_compile_summary_empty():
    assert "No event rows" in compile_session_summary_from_records([])


def test_session_detail_payload():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    t0 = time.time()
    store.record_event(
        user_id="u1",
        session_id="s1",
        record={
            "timestamp": t0,
            "author": "user",
            "model_version": "gemini-2.5-flash",
            "usage": {"prompt_token_count": 10, "candidates_token_count": 2},
            "error_code": None,
            "error_message": None,
            "content_text_sample": "hello",
        },
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    store.record_event(
        user_id="u1",
        session_id="s1",
        record={
            "timestamp": t0 + 5,
            "author": "agent",
            "model_version": "gemini-2.5-flash",
            "usage": {"prompt_token_count": 0, "candidates_token_count": 5},
            "error_code": None,
            "error_message": None,
            "content_text_sample": "reply",
        },
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    p = store.session_detail_payload("u1", "s1")
    assert p is not None
    assert p["session_id"] == "s1"
    assert p["user_id"] == "u1"
    assert p["buffer_event_count"] == 2
    assert p["started_ts"] <= p["ended_ts"]
    assert "user" in p["summary"].lower()
    assert p["disclaimer"]
    assert p["stats"] is not None
    assert p["stats"]["available"] is True
    assert p["stats"]["buffer_events"] == 2
    assert p["stats"]["authors_seen"] == ["user", "agent"]
    assert p["stats"]["tokens_input"] == 10
    assert p["stats"]["tokens_output"] == 7

    missing = store.session_detail_payload("x", "y")
    assert missing is None
    assert p.get("errors_brief") is None


def test_session_detail_payload_includes_errors_brief():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    t0 = time.time()
    store.record_event(
        user_id="u2",
        session_id="s2",
        record={
            "timestamp": t0,
            "author": "system",
            "model_version": "gemini-2.5-flash",
            "usage": {"prompt_token_count": 0, "candidates_token_count": 0},
            "error_code": "TIMEOUT",
            "error_message": "upstream deadline",
            "content_text_sample": None,
        },
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    p = store.session_detail_payload("u2", "s2")
    assert p is not None
    assert p["errors_brief"]
    assert "error-class" in p["errors_brief"].lower()
    assert "TIMEOUT" in p["errors_brief"]


def test_errors_brief_truncates():
    t0 = time.time()
    rec = {
        "timestamp": t0,
        "author": "system",
        "error_code": "NOT_FOUND",
        "error_message": "x" * 400,
        "usage": {"prompt_token_count": 0, "candidates_token_count": 0},
    }
    brief = build_errors_brief([rec], max_msg=80, max_items=2)
    assert brief is not None
    assert "error-class" in brief.lower()
    assert "NOT_FOUND" in brief
    assert len(brief) < 500


def test_session_detail_stats_none_without_timestamps():
    TelemetryStore.reset_for_tests()
    store = TelemetryStore.instance()
    store.record_event(
        user_id="u3",
        session_id="s3",
        record={
            "author": "solo",
            "model_version": "gemini-2.5-flash",
            "usage": {"prompt_token_count": 1, "candidates_token_count": 0},
            "error_code": None,
            "error_message": None,
        },
        default_model="gemini-2.5-flash",
        pricing_config_path=None,
    )
    p = store.session_detail_payload("u3", "s3")
    assert p is not None
    assert p["stats"] is None
    assert "timestamp" in p["summary"].lower()


def test_summary_has_no_timeline_phrase():
    t0 = time.time()
    s = compile_session_summary_from_records(
        [
            {
                "timestamp": t0,
                "author": "a",
                "usage": {"prompt_token_count": 1, "candidates_token_count": 0},
            },
            {
                "timestamp": t0 + 1,
                "author": "b",
                "usage": {"prompt_token_count": 0, "candidates_token_count": 1},
            },
        ]
    )
    assert "Timeline starts" not in s
    assert "Conversation shape" not in s
    assert "authors seen" in s.lower()

"""
Round-trip tests for Firestore reserved-field-name sanitization.

Firestore rejects any field name that starts AND ends with `__` (including
nested map keys). ADK injects `__session_metadata__` into `Session.state`,
and `Event.actions.state_delta` can carry similar names. The session service
encodes these on write and decodes on read; ADK must never see the rename.
"""

from __future__ import annotations

from adktelemetry.firestore.session_service import (
    _DUNDER_PREFIX,
    _decode_key,
    _encode_key,
    _restore_keys,
    _sanitize_keys,
)


def test_encode_only_touches_reserved_pattern():
    assert _encode_key("__session_metadata__") == f"{_DUNDER_PREFIX}session_metadata"
    assert _encode_key("__x__") == f"{_DUNDER_PREFIX}x"
    # Regular keys are unchanged.
    assert _encode_key("state") == "state"
    assert _encode_key("_leading_single") == "_leading_single"
    assert _encode_key("trailing_single_") == "trailing_single_"
    assert _encode_key("__only_prefix") == "__only_prefix"
    assert _encode_key("only_suffix__") == "only_suffix__"
    # Non-strings pass through (Firestore docs tolerate numeric-ish shapes).
    assert _encode_key(42) == 42  # type: ignore[arg-type]


def test_decode_reverses_encode():
    assert _decode_key(_encode_key("__session_metadata__")) == "__session_metadata__"
    assert _decode_key("state") == "state"


def test_sanitize_nested_dict_roundtrip():
    original = {
        "state": {
            "user_flag": True,
            "__session_metadata__": {
                "turn": 1,
                "__inner__": "x",
                "normal": [1, 2, {"__another__": "y"}],
            },
        },
        "other": "unchanged",
    }
    sanitized = _sanitize_keys(original)

    # Top-level unchanged.
    assert "state" in sanitized
    assert "other" in sanitized

    # Reserved nested keys were rewritten.
    inner = sanitized["state"][f"{_DUNDER_PREFIX}session_metadata"]
    assert f"{_DUNDER_PREFIX}inner" in inner
    assert inner["normal"][2][f"{_DUNDER_PREFIX}another"] == "y"

    # Full round-trip equals the original.
    restored = _restore_keys(sanitized)
    assert restored == original


def test_sanitize_preserves_primitive_values():
    payload = {
        "__meta__": {
            "ts": 1234.5,
            "flag": False,
            "list": [None, 1, "x"],
        }
    }
    restored = _restore_keys(_sanitize_keys(payload))
    assert restored == payload


def test_event_serializer_sanitizes_actions_state_delta():
    """Events carrying reserved keys inside actions.state_delta must be
    serializable without hitting the Firestore reserved-field error."""
    from google.adk.events import Event
    from google.adk.events.event_actions import EventActions
    from google.genai import types

    from adktelemetry.firestore.session_service import FirestoreSessionService

    ev = Event(
        author="user",
        content=types.Content(role="user", parts=[types.Part(text="hi")]),
        actions=EventActions(state_delta={"__session_metadata__": {"turn": 7}}),
    )
    payload = FirestoreSessionService._serialize_event(ev)

    # The reserved key disappeared at the wire level...
    import json

    dumped = json.dumps(payload)
    assert "__session_metadata__" not in dumped
    assert _DUNDER_PREFIX in dumped

    # ...but the round-trip rebuilds the original Event semantics.
    restored = FirestoreSessionService._deserialize_event(payload)
    assert restored.actions is not None
    assert restored.actions.state_delta == {"__session_metadata__": {"turn": 7}}

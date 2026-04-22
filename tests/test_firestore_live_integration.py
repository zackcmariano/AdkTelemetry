"""
Optional live integration test against a real Firestore database.

Skipped by default. Enable by pointing the env var `ADKTELEMETRY_FIRESTORE_KEY`
at a service-account JSON key with `roles/datastore.user` on the target
database. Example (agente-teste):

    export ADKTELEMETRY_FIRESTORE_KEY=/path/to/firestore-agent-key.json
    export ADKTELEMETRY_FIRESTORE_DB=agentes-enterprise
    pytest -xvs tests/test_firestore_live_integration.py

This hits the network. It is intentionally NOT part of the default CI run.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

_KEY = os.environ.get("ADKTELEMETRY_FIRESTORE_KEY", "")
_DB = os.environ.get("ADKTELEMETRY_FIRESTORE_DB", "(default)")

pytestmark = pytest.mark.skipif(
    not _KEY or not Path(_KEY).exists(),
    reason="ADKTELEMETRY_FIRESTORE_KEY not set or missing; skipping live integration.",
)


def test_live_firestore_roundtrip():
    from adktelemetry import agentfirestore
    from adktelemetry.firestore.client import reset_clients_for_tests
    from adktelemetry.firestore.config import set_firestore_config
    from adktelemetry.firestore.session_service import FirestoreSessionService

    # Clean module state so this test does not inherit a prior config.
    set_firestore_config(None)  # type: ignore[arg-type]
    reset_clients_for_tests()

    agentfirestore(credentials=_KEY, database=_DB)

    from google.adk.events import Event
    from google.adk.events.event_actions import EventActions
    from google.genai import types

    svc = FirestoreSessionService()
    sid = "pytest-" + uuid.uuid4().hex[:8]

    async def _run():
        sess = await svc.create_session(
            app_name="pytest",
            user_id="tester",
            session_id=sid,
            state={
                "user_flag": True,
                "__session_metadata__": {"turn": 0, "__inner__": "x"},
            },
        )
        try:
            ev = Event(
                author="user",
                content=types.Content(role="user", parts=[types.Part(text="hello")]),
                actions=EventActions(state_delta={"__session_metadata__": {"turn": 1}}),
            )
            await svc.append_event(session=sess, event=ev)

            got = await svc.get_session(
                app_name="pytest", user_id="tester", session_id=sid
            )
            assert got is not None
            assert "__session_metadata__" in got.state
            assert got.state["__session_metadata__"]["__inner__"] == "x"
            assert len(got.events) == 1

            lst = await svc.list_sessions(app_name="pytest", user_id="tester")
            assert any(s.id == sid for s in lst.sessions)
        finally:
            await svc.delete_session(app_name="pytest", user_id="tester", session_id=sid)
            gone = await svc.get_session(
                app_name="pytest", user_id="tester", session_id=sid
            )
            assert gone is None

    asyncio.run(_run())

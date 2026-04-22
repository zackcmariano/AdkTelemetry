"""
FirestoreSessionService - durable ADK sessions on Google Firestore.

Contract (`google.adk.sessions.BaseSessionService`):

    * create_session  (*, app_name, user_id, state=None, session_id=None) -> Session
    * get_session     (*, app_name, user_id, session_id, config=None)     -> Session | None
    * list_sessions   (*, app_name, user_id=None)                         -> ListSessionsResponse
    * delete_session  (*, app_name, user_id, session_id)                  -> None
    * append_event    (session, event)                                    -> Event

Firestore layout (hierarchical, one document per session + subcollection of
events + subcollection of telemetry records):

    /{root_collection}/{app_name}/users/{user_id}/sessions/{session_id}
        fields: id, app_name, user_id, state (map), created_at, last_update_time
        subcollection events/{event_id}    <- full ADK Event snapshot
        subcollection telemetry/{auto_id}  <- AdkTelemetry record mirror

All write paths are async and use the library-scoped singleton `AsyncClient`.
The service delegates state-delta bookkeeping to `BaseSessionService` so the
in-memory `Session` object stays consistent with the persisted doc.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)

from adktelemetry.firestore.client import get_async_client
from adktelemetry.firestore.config import FirestoreConfig, get_firestore_config

logger = logging.getLogger("adktelemetry.firestore.session")


def _now() -> float:
    return time.time()


# Firestore rejects any field name that starts AND ends with `__` (e.g.
# `__session_metadata__`, which ADK injects into session state). We encode
# those keys on write and reverse the transform on read so the ADK layer
# never sees the wire-level rename.
_DUNDER_PREFIX = "akfs_dunder__"


def _encode_key(key: Any) -> Any:
    if isinstance(key, str) and len(key) > 3 and key.startswith("__") and key.endswith("__"):
        return _DUNDER_PREFIX + key[2:-2]
    return key


def _decode_key(key: Any) -> Any:
    if isinstance(key, str) and key.startswith(_DUNDER_PREFIX):
        return "__" + key[len(_DUNDER_PREFIX):] + "__"
    return key


def _sanitize_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {_encode_key(k): _sanitize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_keys(v) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize_keys(v) for v in obj]
    return obj


def _restore_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {_decode_key(k): _restore_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_restore_keys(v) for v in obj]
    return obj


class FirestoreSessionService(BaseSessionService):
    """ADK session backend that persists to Firestore."""

    def __init__(self, config: FirestoreConfig | None = None) -> None:
        super().__init__()
        self._cfg = config or get_firestore_config()
        if self._cfg is None:
            raise RuntimeError(
                "FirestoreSessionService requires a FirestoreConfig. "
                "Call agentfirestore(...) before constructing the session service."
            )

    # ------------------------------------------------------------------ paths
    def _session_ref(self, app_name: str, user_id: str, session_id: str):
        client = get_async_client()
        return (
            client.collection(self._cfg.root_collection)
            .document(app_name)
            .collection("users")
            .document(user_id)
            .collection("sessions")
            .document(session_id)
        )

    def _sessions_col(self, app_name: str, user_id: str):
        client = get_async_client()
        return (
            client.collection(self._cfg.root_collection)
            .document(app_name)
            .collection("users")
            .document(user_id)
            .collection("sessions")
        )

    # ------------------------------------------------------------ serializers
    @staticmethod
    def _serialize_event(event: Event) -> dict[str, Any]:
        # Pydantic v2 - JSON-safe dump (timestamps/enums -> primitives).
        payload = event.model_dump(mode="json", exclude_none=True)
        # Firestore rejects field names starting+ending with `__` (e.g. inside
        # actions.state_delta). Encode on the wire; restored in get_session.
        return _sanitize_keys(payload)

    @staticmethod
    def _deserialize_event(data: dict[str, Any]) -> Event:
        return Event.model_validate(_restore_keys(data))

    # ------------------------------------------------------------ API methods
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = session_id or uuid.uuid4().hex
        now = _now()
        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=dict(state or {}),
            events=[],
            last_update_time=now,
        )
        try:
            await self._session_ref(app_name, user_id, sid).set(
                {
                    "id": sid,
                    "app_name": app_name,
                    "user_id": user_id,
                    "state": _sanitize_keys(session.state),
                    "created_at": now,
                    "last_update_time": now,
                }
            )
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: create_session failed (app=%s user=%s session=%s)",
                app_name,
                user_id,
                sid,
            )
            raise
        logger.debug(
            "AdkTelemetry[firestore]: session created app=%s user=%s session=%s",
            app_name,
            user_id,
            sid,
        )
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        doc_ref = self._session_ref(app_name, user_id, session_id)
        try:
            snap = await doc_ref.get()
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: get_session failed app=%s session=%s",
                app_name,
                session_id,
            )
            return None
        if not snap.exists:
            return None

        data = snap.to_dict() or {}
        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=_restore_keys(dict(data.get("state") or {})),
            events=[],
            last_update_time=float(data.get("last_update_time") or 0.0),
        )

        # Load events ordered by timestamp, applying GetSessionConfig if present.
        events_query = doc_ref.collection("events").order_by("timestamp")
        if config is not None:
            after = getattr(config, "after_timestamp", None)
            if after is not None:
                events_query = events_query.where("timestamp", ">", float(after))

        try:
            events_stream = events_query.stream()
            loaded: list[Event] = []
            async for ev_snap in events_stream:
                try:
                    loaded.append(self._deserialize_event(ev_snap.to_dict() or {}))
                except Exception:
                    logger.exception(
                        "AdkTelemetry[firestore]: failed to deserialize event %s",
                        ev_snap.id,
                    )
            if config is not None and getattr(config, "num_recent_events", None):
                n = int(config.num_recent_events)
                if n > 0:
                    loaded = loaded[-n:]
            session.events = loaded
        except Exception:
            logger.exception("AdkTelemetry[firestore]: failed to load events for %s", session_id)

        return session

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> ListSessionsResponse:
        sessions: list[Session] = []

        if user_id is None:
            # ADK fast_api always passes user_id for /list; if someone passes None
            # we degrade gracefully by returning an empty list rather than doing a
            # cross-user collection-group query (which requires a composite index).
            logger.warning(
                "AdkTelemetry[firestore]: list_sessions called without user_id "
                "(collection-group queries disabled to avoid index requirements)."
            )
            return ListSessionsResponse(sessions=sessions)

        try:
            col = self._sessions_col(app_name, user_id)
            async for snap in col.stream():
                data = snap.to_dict() or {}
                sessions.append(
                    Session(
                        id=snap.id,
                        app_name=app_name,
                        user_id=user_id,
                        state=_restore_keys(dict(data.get("state") or {})),
                        events=[],
                        last_update_time=float(data.get("last_update_time") or 0.0),
                    )
                )
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: list_sessions failed app=%s user=%s",
                app_name,
                user_id,
            )

        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        doc_ref = self._session_ref(app_name, user_id, session_id)
        try:
            # Firestore does not cascade - purge events + telemetry first.
            await self._purge_subcollection(doc_ref, "events")
            await self._purge_subcollection(doc_ref, "telemetry")
            await doc_ref.delete()
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: delete_session failed app=%s session=%s",
                app_name,
                session_id,
            )

    async def append_event(self, session: Session, event: Event) -> Event:
        # Updates session.events / state in-memory (BaseSessionService handles state_delta).
        await super().append_event(session=session, event=event)

        if getattr(event, "partial", False):
            # Partial streaming chunks are not persisted; only final events.
            return event

        doc_ref = self._session_ref(session.app_name, session.user_id, session.id)
        event_ts = float(getattr(event, "timestamp", None) or _now())
        session.last_update_time = event_ts
        event_id = getattr(event, "id", None) or uuid.uuid4().hex

        payload = self._serialize_event(event)
        # Guarantee the ordering field is a number (Firestore can index/range-query).
        payload["timestamp"] = event_ts

        try:
            # Single network round-trip: write the event doc; state + pointer update.
            batch = get_async_client().batch()
            batch.set(doc_ref.collection("events").document(event_id), payload)
            update_fields: dict[str, Any] = {
                "last_update_time": event_ts,
                "state": _sanitize_keys(dict(session.state or {})),
            }
            batch.set(doc_ref, update_fields, merge=True)
            await batch.commit()
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: append_event failed session=%s event=%s",
                session.id,
                event_id,
            )
        return event

    # ----------------------------------------------------------- telemetry mirror
    async def record_telemetry(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        record: dict[str, Any],
    ) -> None:
        """Append one AdkTelemetry record to the session's `telemetry` subcollection."""
        try:
            doc_ref = self._session_ref(app_name, user_id, session_id)
            payload = _sanitize_keys(dict(record))
            if isinstance(payload, dict):
                payload.setdefault("stored_at", _now())
            await doc_ref.collection("telemetry").add(payload)
        except Exception:
            logger.exception(
                "AdkTelemetry[firestore]: telemetry mirror failed session=%s",
                session_id,
            )

    # ----------------------------------------------------------------- helpers
    @staticmethod
    async def _purge_subcollection(doc_ref, name: str, batch_size: int = 400) -> None:
        col = doc_ref.collection(name)
        while True:
            snaps = [s async for s in col.limit(batch_size).stream()]
            if not snaps:
                return
            batch = doc_ref._client.batch()
            for s in snaps:
                batch.delete(s.reference)
            await batch.commit()
            if len(snaps) < batch_size:
                return

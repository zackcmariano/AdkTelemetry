"""
AdkTelemetry - Firestore integration.

Durable ADK session persistence and per-session telemetry logs on Google
Firestore. The rest of AdkTelemetry (dashboard, FinOps, SSE stream) keeps
working unchanged; enabling this module only swaps the session backend from
the in-memory ADK service to Firestore and mirrors telemetry records into a
`telemetry` subcollection keyed by session.
"""

from adktelemetry.firestore.config import FirestoreConfig, get_firestore_config, set_firestore_config
from adktelemetry.firestore.session_service import FirestoreSessionService

__all__ = [
    "FirestoreConfig",
    "FirestoreSessionService",
    "get_firestore_config",
    "set_firestore_config",
]

"""
AdkTelemetry - `agentfirestore()` public entrypoint.

Symmetrical to `agentelemetry()`: one function call at process startup wires
Firestore as the ADK session backend and turns on per-session telemetry
mirroring. The developer never touches google-cloud-firestore directly -
credentials, client, session service, and runner hooks are all installed here.

Usage:

    from adktelemetry import agentelemetry, agentfirestore

    agentelemetry(modelkey=_api_key, adkmodel="gemini-2.5-flash")
    agentfirestore(
        credentials="keys/firestore-agent-key.json",
        database="agentes-enterprise",
    )

Both calls are idempotent and independent: use telemetry alone for local dev,
or add Firestore when you need durable conversations + cross-process logs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from adktelemetry.firestore.client import build_config_from_user_input
from adktelemetry.firestore.config import set_firestore_config
from adktelemetry.hooks import ensure_runner_patch
from adktelemetry.patch_cli import ensure_firestore_session_patch

logger = logging.getLogger("adktelemetry.agentfirestore")


def agentfirestore(
    *,
    credentials: str | Path | dict[str, Any] | None = None,
    database: str = "(default)",
    project_id: str | None = None,
    root_collection: str = "adk_agents",
    mirror_telemetry: bool = True,
    rehydrate_on_startup: bool = True,
) -> None:
    """
    Enable durable ADK sessions + per-session telemetry logs on Firestore.

    Args:
        credentials: Path to a GCP service account JSON key, or an already
            parsed dict, or `None` to use Application Default Credentials
            (GKE workload identity, GCE metadata, `gcloud auth application-default login`).
        database: Firestore database id. Default `(default)`. Use the exact id
            shown in the GCP console (e.g. `agentes-enterprise`).
        project_id: Optional override. Auto-detected from the service account
            key when omitted.
        root_collection: Top-level collection name where sessions live.
            Default `adk_agents`. Layout:
            `/{root}/{app_name}/users/{user_id}/sessions/{session_id}`.
        mirror_telemetry: When True (default) and `agentelemetry()` is also
            enabled, every telemetry record is asynchronously mirrored into
            the session's `telemetry` subcollection.
        rehydrate_on_startup: Reserved for future dashboard rehydration from
            Firestore on process boot. Currently tracked in config; runtime
            reads always go through the `FirestoreSessionService`.

    Side effects:
        * Registers the runner hook (same as `agentelemetry()`; idempotent).
        * Patches `AdkWebServer.__init__` to swap `session_service` for a
          `FirestoreSessionService` on the next `adk web` startup.
        * Lazily constructs a singleton `firestore.AsyncClient` on first use.

    Raises:
        ValueError: when neither `project_id` nor a resolvable credential is provided.
        RuntimeError: when `google-cloud-firestore` is not installed.
            Install with: `pip install 'adktelemetry[firestore]'`.
    """
    cfg = build_config_from_user_input(
        credentials=credentials,
        database=database,
        project_id=project_id,
        root_collection=root_collection,
        mirror_telemetry=mirror_telemetry,
        rehydrate_on_startup=rehydrate_on_startup,
    )
    set_firestore_config(cfg)

    # Idempotent: same hook agentelemetry() installs. Safe to call either order.
    ensure_runner_patch()
    # Idempotent: wires the FirestoreSessionService into AdkWebServer on next boot.
    ensure_firestore_session_patch()

    logger.info(
        "AdkTelemetry[firestore] enabled (%s). Sessions + telemetry will persist to Firestore.",
        cfg.describe(),
    )

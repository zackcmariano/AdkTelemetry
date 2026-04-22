"""
Firestore client factory.

Singleton sync + async clients built from `FirestoreConfig`. Credentials are
resolved in this priority order:

1. `credentials_info` (dict, e.g. loaded from Secret Manager).
2. `credentials_path` (JSON key on disk - dev/local).
3. Application Default Credentials (ADC), when both are None.

The factory is lazy so that importing `adktelemetry` does not touch Firestore
and the optional dependency `google-cloud-firestore` only breaks at
`agentfirestore()` time if the extra was not installed.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from adktelemetry.firestore.config import FirestoreConfig, get_firestore_config

logger = logging.getLogger("adktelemetry.firestore.client")

_async_client: Any = None
_sync_client: Any = None
_lock = threading.Lock()


class FirestoreNotConfiguredError(RuntimeError):
    """Raised when client access is requested without a FirestoreConfig."""


def _load_credentials(cfg: FirestoreConfig):
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        raise RuntimeError(
            "adktelemetry[firestore] requires 'google-auth'. "
            "Install with: pip install 'adktelemetry[firestore]'"
        ) from e

    if cfg.credentials_info:
        return service_account.Credentials.from_service_account_info(cfg.credentials_info)
    if cfg.credentials_path:
        path = Path(cfg.credentials_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Firestore service account key not found: {path}")
        return service_account.Credentials.from_service_account_file(str(path))
    # ADC fallback (e.g. GKE workload identity, GCE metadata server).
    return None


def _resolve_project(cfg: FirestoreConfig) -> str:
    if cfg.project_id:
        return cfg.project_id
    if cfg.credentials_info:
        return cfg.credentials_info.get("project_id") or ""
    if cfg.credentials_path:
        try:
            with open(cfg.credentials_path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            return data.get("project_id", "") or ""
        except Exception:
            logger.exception("AdkTelemetry[firestore]: could not read project_id from key file")
    return ""


def build_config_from_user_input(
    *,
    credentials: str | dict[str, Any] | None,
    database: str,
    project_id: str | None,
    root_collection: str,
    mirror_telemetry: bool,
    rehydrate_on_startup: bool,
) -> FirestoreConfig:
    """Normalize the user-facing `agentfirestore()` arguments into a config."""

    credentials_path: str | None = None
    credentials_info: dict[str, Any] | None = None
    if isinstance(credentials, dict):
        credentials_info = dict(credentials)
    elif isinstance(credentials, (str, Path)):
        credentials_path = str(credentials)

    resolved_project = project_id or ""
    if not resolved_project and credentials_info:
        resolved_project = credentials_info.get("project_id") or ""
    if not resolved_project and credentials_path:
        try:
            with open(credentials_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            resolved_project = data.get("project_id", "") or ""
        except Exception:
            logger.warning(
                "AdkTelemetry[firestore]: could not auto-detect project_id from %s",
                credentials_path,
            )

    if not resolved_project:
        raise ValueError(
            "agentfirestore(): could not resolve GCP project_id. "
            "Pass `project_id=` explicitly or provide credentials with a project_id field."
        )

    return FirestoreConfig(
        project_id=resolved_project,
        database=database or "(default)",
        root_collection=root_collection or "adk_agents",
        credentials_path=credentials_path,
        credentials_info=credentials_info,
        mirror_telemetry=mirror_telemetry,
        rehydrate_on_startup=rehydrate_on_startup,
    )


def get_async_client():
    """Returns a singleton `google.cloud.firestore.AsyncClient`."""
    global _async_client
    if _async_client is not None:
        return _async_client
    with _lock:
        if _async_client is not None:
            return _async_client
        cfg = get_firestore_config()
        if cfg is None:
            raise FirestoreNotConfiguredError(
                "Firestore not configured. Call agentfirestore(...) at startup."
            )
        try:
            from google.cloud import firestore  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "adktelemetry[firestore] requires 'google-cloud-firestore'. "
                "Install with: pip install 'adktelemetry[firestore]'"
            ) from e

        _async_client = firestore.AsyncClient(
            project=_resolve_project(cfg) or cfg.project_id,
            credentials=_load_credentials(cfg),
            database=cfg.database,
        )
        logger.info("AdkTelemetry[firestore]: AsyncClient ready (%s)", cfg.describe())
        return _async_client


def get_sync_client():
    """Returns a singleton `google.cloud.firestore.Client` (sync, for rehydrate)."""
    global _sync_client
    if _sync_client is not None:
        return _sync_client
    with _lock:
        if _sync_client is not None:
            return _sync_client
        cfg = get_firestore_config()
        if cfg is None:
            raise FirestoreNotConfiguredError(
                "Firestore not configured. Call agentfirestore(...) at startup."
            )
        try:
            from google.cloud import firestore  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "adktelemetry[firestore] requires 'google-cloud-firestore'."
            ) from e

        _sync_client = firestore.Client(
            project=_resolve_project(cfg) or cfg.project_id,
            credentials=_load_credentials(cfg),
            database=cfg.database,
        )
        logger.info("AdkTelemetry[firestore]: sync Client ready")
        return _sync_client


def reset_clients_for_tests() -> None:
    global _async_client, _sync_client
    _async_client = None
    _sync_client = None

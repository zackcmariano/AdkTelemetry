"""
Runtime configuration for the Firestore integration.

Set once by `agentfirestore()` at process startup and read by the session
service, the telemetry mirror, and the AdkWebServer patch. Keeping the config
in a dedicated slot (instead of environment variables) matches the
`agentelemetry()` contract: all complexity lives inside the library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FirestoreConfig:
    """Immutable-ish snapshot of Firestore runtime settings."""

    project_id: str
    database: str = "(default)"
    root_collection: str = "adk_agents"
    credentials_path: str | None = None
    credentials_info: dict[str, Any] | None = None
    mirror_telemetry: bool = True
    rehydrate_on_startup: bool = True
    rehydrate_max_sessions: int = 100
    rehydrate_max_events_per_session: int = 500
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return (
            f"project={self.project_id} database={self.database} "
            f"root={self.root_collection} mirror_telemetry={self.mirror_telemetry}"
        )


_CONFIG: FirestoreConfig | None = None


def set_firestore_config(cfg: FirestoreConfig) -> None:
    global _CONFIG
    _CONFIG = cfg


def get_firestore_config() -> FirestoreConfig | None:
    return _CONFIG


def is_enabled() -> bool:
    return _CONFIG is not None

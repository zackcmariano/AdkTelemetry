from adktelemetry.runtime import ensure_project_root

ensure_project_root()

from adktelemetry.agentelemetry import agentelemetry
from adktelemetry.autoagent import autoagent

__all__ = ["agentelemetry", "autoagent", "ensure_project_root"]

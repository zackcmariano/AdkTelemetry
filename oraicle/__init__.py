# oraicle/__init__.py

from .runtime import ensure_project_root

# roda automaticamente ao importar oraicle
ensure_project_root()

from .autoagent import autoagent

__all__ = ["autoagent"]

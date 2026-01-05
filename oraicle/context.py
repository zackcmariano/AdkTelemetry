# oraicle/context.py
import sys
from pathlib import Path

_APP_ROOT_MARKERS = {"app", "config", "tools", "utils"}


def inject_app_root(start_path: Path):
    current = start_path.resolve()

    while current != current.parent:
        if any((current / marker).exists() for marker in _APP_ROOT_MARKERS):
            if str(current) not in sys.path:
                sys.path.insert(0, str(current))
            return current
        current = current.parent

    return None

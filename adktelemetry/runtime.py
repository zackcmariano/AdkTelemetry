import sys
from pathlib import Path


def ensure_project_root(start: Path | None = None) -> Path | None:
    """
    Ensures the project root (parent of `app/`) is on sys.path for ADK layouts.
    """
    start_path = (start or Path.cwd()).resolve()

    for p in [start_path, *start_path.parents]:
        app_pkg = p / "app" / "__init__.py"
        if app_pkg.exists():
            root_str = str(p)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return p

    return None

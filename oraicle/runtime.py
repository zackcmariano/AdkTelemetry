# oraicle/runtime.py

import sys
from pathlib import Path


def ensure_project_root(start: Path | None = None) -> Path | None:
    """
    Garante que o diretório raiz do projeto (pai do 'app/') esteja no sys.path.
    Isso faz com que 'import app.tools...' funcione mesmo quando o cwd é 'app/'.

    Estratégia:
    - Sobe a partir do cwd (ou start) até encontrar um diretório que contenha:
        app/__init__.py
    - Insere esse diretório no sys.path (posição 0)
    """
    start_path = (start or Path.cwd()).resolve()

    for p in [start_path, *start_path.parents]:
        app_pkg = p / "app" / "__init__.py"
        if app_pkg.exists():
            root = p
            root_str = str(root)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return root

    return None

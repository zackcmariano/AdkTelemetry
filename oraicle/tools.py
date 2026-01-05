# oraicle/tools.py

import importlib
import pkgutil
from types import ModuleType
from pathlib import Path
from .runtime import ensure_project_root


def _discover_tools():
    """
    Dynamically discovers and loads all tools from app/tools.
    """
    ensure_project_root()

    try:
        tools_pkg = importlib.import_module("app.tools")
    except ModuleNotFoundError:
        raise RuntimeError(
            "Oraicle-Agent could not find 'app.tools'. "
            "Make sure your project follows the app/tools structure."
        )

    tools_path = Path(tools_pkg.__file__).parent
    exported = {}

    for module_info in pkgutil.iter_modules([str(tools_path)]):
        module_name = f"app.tools.{module_info.name}"
        module = importlib.import_module(module_name)

        # 1️⃣ Se o módulo define __all__, respeita
        if hasattr(module, "__all__"):
            for name in module.__all__:
                exported[name] = getattr(module, name)
        else:
            # 2️⃣ Caso contrário, exporta funções públicas
            for attr in dir(module):
                if attr.startswith("_"):
                    continue
                obj = getattr(module, attr)
                if callable(obj):
                    exported[attr] = obj

    return exported


# 🔥 Exporta tudo dinamicamente
_globals = _discover_tools()
globals().update(_globals)

__all__ = list(_globals.keys())

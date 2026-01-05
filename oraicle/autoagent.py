# oraicle/autoagent.py

import inspect
from pathlib import Path

from oraicle.registry import AgentRegistry
from oraicle.context import inject_app_root


def autoagent(agent):
    """
    Promotes an Agent to a semantic root agent.

    What this does:
    1. Discovers the real caller module and file path
    2. Injects the application root into sys.path
       (enables sub_agents to access app-level modules)
    3. Registers the agent in Oraicle's semantic registry
    4. Injects `root_agent` into the caller module
       to fully satisfy Google-ADK loader expectations
    """

    # ─────────────────────────────────────────────
    # 1. Discover caller context
    # ─────────────────────────────────────────────
    caller_frame = inspect.stack()[1]
    caller_module = inspect.getmodule(caller_frame.frame)

    if caller_module is None or not hasattr(caller_module, "__file__"):
        raise RuntimeError(
            "autoagent() must be called from a Python module file."
        )

    caller_file = Path(caller_module.__file__).resolve()
    module_name = caller_module.__name__

    # ─────────────────────────────────────────────
    # 2. Inject application root into sys.path
    # ─────────────────────────────────────────────
    inject_app_root(caller_file.parent)

    # ─────────────────────────────────────────────
    # 3. Semantic registry (Oraicle internal)
    # ─────────────────────────────────────────────
    AgentRegistry.register_root(
        agent,
        file_path=str(caller_file),
        module_name=module_name,
    )

    # ─────────────────────────────────────────────
    # 4. Google-ADK compatibility layer
    # ─────────────────────────────────────────────
    # ADK loader expects `root_agent` to exist
    setattr(caller_module, "root_agent", agent)

    return agent

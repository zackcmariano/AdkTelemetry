import inspect
from pathlib import Path

from adktelemetry.context import inject_app_root
from adktelemetry.registry import AgentRegistry


def autoagent(agent):
    """
    Promotes an Agent to a semantic root agent (Google ADK loader compatibility).
    """
    caller_frame = inspect.stack()[1]
    caller_module = inspect.getmodule(caller_frame.frame)

    if caller_module is None or not hasattr(caller_module, "__file__"):
        raise RuntimeError("autoagent() must be called from a Python module file.")

    caller_file = Path(caller_module.__file__).resolve()
    module_name = caller_module.__name__

    inject_app_root(caller_file.parent)

    AgentRegistry.register_root(
        agent,
        file_path=str(caller_file),
        module_name=module_name,
    )

    setattr(caller_module, "root_agent", agent)

    return agent

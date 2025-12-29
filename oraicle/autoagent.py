# oraicle/autoagent.py
import inspect
from oraicle.registry import AgentRegistry

def autoagent(agent):
    """
    Registers an Agent as a root agent AND
    injects root_agent into the caller module
    to satisfy Google-ADK loader.
    """
    # 1. Registra no registry Oraicle
    AgentRegistry.register_root(agent)

    # 2. Descobre o módulo chamador
    caller_frame = inspect.stack()[1]
    caller_module = inspect.getmodule(caller_frame.frame)

    if caller_module is not None:
        # 3. Injeta root_agent no namespace do módulo
        setattr(caller_module, "root_agent", agent)

    return agent

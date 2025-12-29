from oraicle.registry import AgentRegistry
from oraicle.exceptions import NoRootAgentRegistered

def resolve_root_agent():
    roots = AgentRegistry.all_roots()

    if not roots:
        raise NoRootAgentRegistered(
            "Nenhum root_agent registrado. Use autoagent(agent)."
        )

    return list(roots.values())[0]


root_agent = resolve_root_agent()

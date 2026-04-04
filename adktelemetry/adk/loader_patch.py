"""
Semantic loader patch for Google ADK (multiple root agents).
"""

from adktelemetry.exceptions import NoRootAgentRegistered
from adktelemetry.registry import AgentRegistry


def resolve_root_agent(agent_name: str | None = None):
    roots = AgentRegistry.all_roots()

    if not roots:
        raise NoRootAgentRegistered("No root_agent registered. Use autoagent(agent).")

    if agent_name:
        registered = AgentRegistry.get_root(agent_name)
        if registered:
            return registered.agent

        raise NoRootAgentRegistered(f"Root agent '{agent_name}' not found in registry.")

    return next(iter(roots.values())).agent


try:
    root_agent = resolve_root_agent()
except NoRootAgentRegistered:
    root_agent = None

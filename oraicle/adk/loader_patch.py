# oraicle/adk/loader_patch.py

"""
Oraicle semantic loader patch for Google ADK.

This module enables:
- Multiple semantic root agents
- Root agent resolution outside filesystem boundaries
- Compatibility with ADK Web "Select an agent"
"""

from oraicle.registry import AgentRegistry
from oraicle.exceptions import NoRootAgentRegistered


def resolve_root_agent(agent_name: str | None = None):
    """
    Resolves a root agent semantically.

    If agent_name is provided:
        - Return the matching registered root agent
    If agent_name is None:
        - Return the first registered root agent (fallback behavior)
    """

    roots = AgentRegistry.all_roots()

    if not roots:
        raise NoRootAgentRegistered(
            "No root_agent registered. Use autoagent(agent)."
        )

    # Explicit selection (used by ADK loader)
    if agent_name:
        registered = AgentRegistry.get_root(agent_name)
        if registered:
            return registered.agent

        raise NoRootAgentRegistered(
            f"Root agent '{agent_name}' not found in Oraicle registry."
        )

    # Fallback (backward-compatible behavior)
    return next(iter(roots.values())).agent


# Default export for ADK compatibility
# ADK expects `root_agent` at import time
try:
    root_agent = resolve_root_agent()
except NoRootAgentRegistered:
    # Allow ADK to continue scanning other modules
    root_agent = None

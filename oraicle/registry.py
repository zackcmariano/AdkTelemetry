# oraicle/registry.py

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RegisteredAgent:
    name: str
    agent: object
    file_path: str
    module_name: str


class AgentRegistry:
    """
    Central semantic registry for Oraicle root agents.
    This is NOT filesystem-based.
    """

    _root_agents: Dict[str, RegisteredAgent] = {}

    @classmethod
    def register_root(cls, agent, *, file_path: str, module_name: str):
        cls._root_agents[agent.name] = RegisteredAgent(
            name=agent.name,
            agent=agent,
            file_path=file_path,
            module_name=module_name,
        )

    @classmethod
    def get_root(cls, name: str) -> Optional[RegisteredAgent]:
        return cls._root_agents.get(name)

    @classmethod
    def all_roots(cls) -> Dict[str, RegisteredAgent]:
        return dict(cls._root_agents)

    @classmethod
    def exists(cls, name: str) -> bool:
        return name in cls._root_agents

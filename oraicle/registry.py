# oraicle/registry.py

class AgentRegistry:
    _root_agents = {}

    @classmethod
    def register_root(cls, agent):
        cls._root_agents[agent.name] = agent

    @classmethod
    def get_root(cls, name):
        return cls._root_agents.get(name)

    @classmethod
    def all_roots(cls):
        return cls._root_agents

from adktelemetry.autoagent import autoagent
from adktelemetry.registry import AgentRegistry

class DummyAgent:
    def __init__(self, name):
        self.name = name


def test_autoagent_registers_agent():
    AgentRegistry._root_agents.clear()

    agent = DummyAgent("auto_test")
    returned = autoagent(agent)

    assert returned == agent
    reg = AgentRegistry.get_root("auto_test")
    assert reg is not None and reg.agent == agent

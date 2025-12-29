from oraicle.registry import AgentRegistry

class DummyAgent:
    def __init__(self, name):
        self.name = name


def test_register_and_get_root():
    agent = DummyAgent("agent_test")
    AgentRegistry.register_root(agent)

    assert AgentRegistry.get_root("agent_test") == agent


def test_all_roots():
    AgentRegistry._root_agents.clear()

    a1 = DummyAgent("a1")
    a2 = DummyAgent("a2")

    AgentRegistry.register_root(a1)
    AgentRegistry.register_root(a2)

    roots = AgentRegistry.all_roots()
    assert len(roots) == 2
    assert "a1" in roots
    assert "a2" in roots

from adktelemetry.exceptions import NoRootAgentRegistered
from adktelemetry.adk.loader_patch import resolve_root_agent
from adktelemetry.registry import AgentRegistry

class DummyAgent:
    def __init__(self, name):
        self.name = name


def test_resolve_root_agent_success():
    AgentRegistry._root_agents.clear()

    agent = DummyAgent("root_ok")
    AgentRegistry.register_root(agent, file_path="/tmp/t.py", module_name="t")

    root = resolve_root_agent()
    assert root == agent


def test_resolve_root_agent_fail():
    AgentRegistry._root_agents.clear()

    try:
        resolve_root_agent()
        assert False, "Expected NoRootAgentRegistered exception"
    except NoRootAgentRegistered:
        assert True

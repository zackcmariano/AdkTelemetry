# oraicle/exceptions.py

class OraicleError(Exception):
    """Erro base da Oraicle Agent."""
    pass


class NoRootAgentRegistered(OraicleError):
    """Nenhum root_agent foi registrado via autoagent()."""
    pass


class MultipleRootAgentsError(OraicleError):
    """Erro ao tentar resolver múltiplos root_agents sem estratégia."""
    pass


class InvalidAgentError(OraicleError):
    """Objeto fornecido não é um Agent válido do Google-ADK."""
    pass

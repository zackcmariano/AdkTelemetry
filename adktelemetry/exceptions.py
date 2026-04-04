class AdkTelemetryError(Exception):
    """Base error for AdkTelemetry."""


class NoRootAgentRegistered(AdkTelemetryError):
    """No root agent registered via autoagent()."""


class MultipleRootAgentsError(AdkTelemetryError):
    """Multiple root agents without a resolution strategy."""


class InvalidAgentError(AdkTelemetryError):
    """Provided object is not a valid Google ADK agent."""

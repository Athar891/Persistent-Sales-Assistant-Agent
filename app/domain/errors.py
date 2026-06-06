"""Domain errors that the API layer maps to RFC 9457 Problem Details.

Raising one of these from a service/adapter lets the single global handler render a
consistent ``application/problem+json`` body without leaking stack traces.
"""


class AgentError(Exception):
    """Base class for expected, user-facing failures."""

    status: int = 500
    title: str = "Internal Server Error"


class ConfigurationError(AgentError):
    """A required dependency (e.g. the Anthropic API key) is missing."""

    status = 503
    title = "Service Not Configured"


class UpstreamLLMError(AgentError):
    """The Anthropic API returned an error or was unreachable."""

    status = 502
    title = "Upstream LLM Error"

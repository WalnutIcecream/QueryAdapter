"""Typed, actionable errors for QueryAdapter.

Every error raised by the public API derives from :class:`QueryAdapterError`,
so integrations can catch a single base type while more specific handlers
recover from individual failure modes.
"""


class QueryAdapterError(Exception):
    """Base class for all QueryAdapter errors."""


class ConfigurationError(QueryAdapterError):
    """The adapter was constructed with invalid or missing configuration."""


class ConnectionError(QueryAdapterError):
    """A database could not be reached or a driver is missing."""


class SchemaError(QueryAdapterError):
    """Schema introspection failed or produced unusable metadata."""


class ProviderError(QueryAdapterError):
    """An LLM provider failed, timed out, or returned an invalid response."""


class IntentResolutionError(QueryAdapterError):
    """Natural language could not be resolved to a query intent."""


class AmbiguityError(IntentResolutionError):
    """Intent resolution found multiple plausible mappings for a term."""


class ValidationError(QueryAdapterError):
    """A generated query violated schema, type, or capability constraints."""


class UnsupportedOperationError(QueryAdapterError):
    """The requested operation is not supported by the target database."""


class SafetyError(QueryAdapterError):
    """A query was blocked by the read-only safety policy."""


class ExecutionError(QueryAdapterError):
    """A generated query executed but the database rejected it."""

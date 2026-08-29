"""QueryAdapter — natural-language querying for SQL, NoSQL, and graph databases.

Minimal integration::

    from queryadapter import QueryAdapter

    adapter = QueryAdapter("path/to/app.db")
    result = adapter.ask("Show my top customers")

    print(result.data)      # normalized rows
    print(result.query)     # generated native query
"""

from queryadapter.core import QueryAdapter
from queryadapter.result import Result
from queryadapter.config import QueryAdapterConfig
from queryadapter.errors import (
    QueryAdapterError,
    ConfigurationError,
    ConnectionError,
    SchemaError,
    ProviderError,
    IntentResolutionError,
    AmbiguityError,
    ValidationError,
    UnsupportedOperationError,
    SafetyError,
    ExecutionError,
)

__version__ = "0.1.0"

__all__ = [
    "QueryAdapter",
    "Result",
    "QueryAdapterConfig",
    "QueryAdapterError",
    "ConfigurationError",
    "ConnectionError",
    "SchemaError",
    "ProviderError",
    "IntentResolutionError",
    "AmbiguityError",
    "ValidationError",
    "UnsupportedOperationError",
    "SafetyError",
    "ExecutionError",
]

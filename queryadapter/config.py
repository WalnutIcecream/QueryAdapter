"""Configuration models for QueryAdapter."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class QueryAdapterConfig:
    """Runtime configuration for a QueryAdapter instance.

    Fields mirror the constructor arguments; keeping them in a dataclass
    makes the config inspectable and serializable without pulling in a web
    framework or config library.
    """

    db_type: str = "sqlite"
    provider: str = "ollama"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    read_only: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    cache_ttl: int = 300
    default_limit: Optional[int] = None
    max_limit: int = 1000
    allow_schema_send: bool = True
    allow_results_send: bool = True
    allow_query_log: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "db_type": self.db_type,
            "provider": self.provider,
            "model": self.model,
            "read_only": self.read_only,
            "cache_ttl": self.cache_ttl,
            "default_limit": self.default_limit,
            "max_limit": self.max_limit,
        }

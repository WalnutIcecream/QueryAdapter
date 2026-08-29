"""Schema metadata caching with TTL-based invalidation."""

import time
from typing import Any


class SchemaCache:
    """Small in-process cache for discovered schema metadata.

    Introspection can be expensive (network round-trips for MongoDB/Neo4j),
    so results are cached and reused until their TTL expires. Entries can be
    invalidated explicitly when the underlying schema is known to change.
    """

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._collections: Any = None
        self._ddl: Any = None
        self._collections_at: float = 0.0
        self._ddl_at: float = 0.0

    def _fresh(self, ts: float) -> bool:
        # A non-positive TTL means caching is disabled (always expire).
        if self.ttl <= 0:
            return False
        return (time.time() - ts) < self.ttl

    def get_collections(self) -> Any:
        if self._collections is not None and self._fresh(self._collections_at):
            return self._collections
        return None

    def get_ddl(self) -> Any:
        if self._ddl is not None and self._fresh(self._ddl_at):
            return self._ddl
        return None

    def set_collections(self, value: Any) -> None:
        self._collections = value
        self._collections_at = time.time()

    def set_ddl(self, value: Any) -> None:
        self._ddl = value
        self._ddl_at = time.time()

    def invalidate(self) -> None:
        self._collections = None
        self._ddl = None
        self._collections_at = 0.0
        self._ddl_at = 0.0

"""Normalized query results across heterogeneous backends."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Result:
    """A structured, backend-normalized query result.

    Attributes:
        data: Normalized rows/documents. For tabular backends this is a list of
            dicts or tuples; for graph backends this preserves node/relationship
            records rather than flattening everything into rows.
        columns: Ordered column names for tabular results, or the equivalent
            projection keys when available. Empty for graph-native results.
        query: The generated native query (SQL, aggregation pipeline, or
            Cypher), for inspection and debugging.
        database: Backend name, e.g. ``"sqlite"``, ``"mongodb"``, ``"neo4j"``.
        intent: The resolved intent payload used to produce the query.
        execution_time: Wall-clock time for query execution in seconds.
        row_count: Number of top-level records returned.
        metadata: Arbitrary backend/provided metadata.
        warnings: Non-fatal diagnostics collected during the pipeline.
        native: The raw backend result object, when available.
    """

    data: Any = None
    columns: list[str] = field(default_factory=list)
    query: Any = None
    database: str = ""
    intent: Optional[dict] = None
    execution_time: Optional[float] = None
    row_count: int = 0
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    native: Any = None

    def __len__(self) -> int:
        try:
            return len(self.data)
        except TypeError:
            return 0

    def __iter__(self):
        return iter(self.data or [])

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "columns": self.columns,
            "query": self.query,
            "database": self.database,
            "execution_time": self.execution_time,
            "row_count": self.row_count,
            "metadata": self.metadata,
            "warnings": self.warnings,
        }

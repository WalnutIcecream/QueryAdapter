"""
queryadapter.ir — Intermediate Representation.

The QueryPlan is the universal JSON structure that every backend consumes.
It's produced by the NLP model (T5 or Ollama), normalized, validated against
the target database schema, then sent to a backend-specific constructor.
"""

from queryadapter.ir.query_plan import (
    QueryPlan,
    Filter,
    Join,
    Aggregation,
    OrderBy,
    MatchPattern,
    IRValidationError,
    validate_plan_structure,
)
from queryadapter.ir.validator import (
    validate_against_schema,
    SchemaValidationError,
)

__all__ = [
    "QueryPlan",
    "Filter",
    "Join",
    "Aggregation",
    "OrderBy",
    "MatchPattern",
    "IRValidationError",
    "validate_plan_structure",
    "validate_against_schema",
    "SchemaValidationError",
]

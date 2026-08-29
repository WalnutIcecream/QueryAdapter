"""Unified Query Intermediate Representation (IR) for multi-backend support.

The QueryPlan is the common JSON structure produced by the NLP model
and consumed by backend-specific query constructors (SQL, MQL, Cypher).
"""

from dataclasses import dataclass, field
from typing import Optional, Any

ALLOWED_ACTIONS = {"SELECT"}
ALLOWED_DB_TYPES = {"sqlite", "mongodb", "neo4j"}


class IRValidationError(ValueError):
    """Raised when a QueryPlan has missing required fields or invalid values."""
    pass


@dataclass
class Filter:
    column: str
    operator: str
    value: Any = None

    def to_dict(self):
        return {"column": self.column, "operator": self.operator, "value": self.value}

    @classmethod
    def from_dict(cls, d):
        return cls(column=d["column"], operator=d["operator"], value=d.get("value"))


@dataclass
class Join:
    type: str = "INNER"
    table: str = ""
    on: dict = field(default_factory=dict)

    def to_dict(self):
        return {"type": self.type, "table": self.table, "on": self.on}

    @classmethod
    def from_dict(cls, d):
        return cls(type=d.get("type", "INNER"), table=d["table"], on=d.get("on", {}))


@dataclass
class Aggregation:
    function: str
    column: str
    alias: Optional[str] = None

    def to_dict(self):
        d = {"function": self.function, "column": self.column}
        if self.alias:
            d["alias"] = self.alias
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(function=d["function"], column=d["column"], alias=d.get("alias"))


@dataclass
class OrderBy:
    column: str
    direction: str = "ASC"

    def to_dict(self):
        return {"column": self.column, "direction": self.direction}

    @classmethod
    def from_dict(cls, d):
        return cls(column=d["column"], direction=d.get("direction", "ASC"))


@dataclass
class MatchPattern:
    """Neo4j-specific: a MATCH pattern like (n:Label) or (a)-[:REL]->(b)."""
    variable: str
    labels: list[str] = field(default_factory=list)
    relationship_types: list[str] = field(default_factory=list)
    direction: str = "OUTGOING"
    min_hops: int = 1
    max_hops: int = 1
    optional: bool = False
    properties: dict = field(default_factory=dict)
    from_variable: Optional[str] = None
    to_variable: Optional[str] = None

    def to_dict(self):
        d = {"variable": self.variable}
        if self.labels:
            d["labels"] = self.labels
        if self.relationship_types:
            d["relationship_types"] = self.relationship_types
            d["direction"] = self.direction
            d["min_hops"] = self.min_hops
            d["max_hops"] = self.max_hops
            d["from_variable"] = self.from_variable
            d["to_variable"] = self.to_variable
        if self.optional:
            d["optional"] = True
        if self.properties:
            d["properties"] = self.properties
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            variable=d["variable"],
            labels=d.get("labels", []),
            relationship_types=d.get("relationship_types", []),
            direction=d.get("direction", "OUTGOING"),
            min_hops=d.get("min_hops", 1),
            max_hops=d.get("max_hops", 1),
            optional=d.get("optional", False),
            properties=d.get("properties", {}),
            from_variable=d.get("from_variable"),
            to_variable=d.get("to_variable"),
        )


@dataclass
class QueryPlan:
    """Unified query plan that all backends consume.

    Core fields map 1:1 to the existing SQL IR. Backend-specific fields are
    optional and only used by the relevant constructor.
    """
    action: str = "SELECT"
    db_type: str = "sqlite"

    # ── Core (all backends) ──
    table: str = ""
    columns: list[str] = field(default_factory=list)
    distinct: bool = False
    joins: list[Join] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    having: list[Filter] = field(default_factory=list)
    aggregations: list[Aggregation] = field(default_factory=list)
    order_by: list[OrderBy] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    where_logic: str = "AND"
    having_logic: str = "AND"

    # ── MongoDB-specific ──
    unwind: Optional[str] = None
    include_id: bool = True

    # ── Neo4j-specific (future) ──
    match_patterns: list[MatchPattern] = field(default_factory=list)
    return_expressions: list[dict] = field(default_factory=list)

    def to_dict(self):
        d = {
            "action": self.action,
            "db_type": self.db_type,
            "table": self.table,
            "columns": self.columns,
            "distinct": self.distinct,
            "joins": [j.to_dict() for j in self.joins],
            "filters": [f.to_dict() for f in self.filters],
            "group_by": self.group_by,
            "having": [h.to_dict() for h in self.having],
            "aggregations": [a.to_dict() for a in self.aggregations],
            "order_by": [o.to_dict() for o in self.order_by],
            "limit": self.limit,
            "offset": self.offset,
            "where_logic": self.where_logic,
            "having_logic": self.having_logic,
        }
        if self.unwind:
            d["unwind"] = self.unwind
        if not self.include_id:
            d["include_id"] = False
        if self.match_patterns:
            d["match_patterns"] = [m.to_dict() for m in self.match_patterns]
        if self.return_expressions:
            d["return_expressions"] = self.return_expressions
        return d

    @classmethod
    def from_dict(cls, d):
        plan = cls(
            action=d.get("action", "SELECT"),
            db_type=d.get("db_type", "sqlite"),
            table=d.get("table", ""),
            columns=d.get("columns", []),
            distinct=d.get("distinct", False),
            joins=[Join.from_dict(j) for j in d.get("joins", [])],
            filters=[Filter.from_dict(f) for f in d.get("filters", [])],
            group_by=d.get("group_by", []),
            having=[Filter.from_dict(h) for h in d.get("having", [])],
            aggregations=[Aggregation.from_dict(a) for a in d.get("aggregations", [])],
            order_by=[OrderBy.from_dict(o) for o in d.get("order_by", [])],
            limit=d.get("limit"),
            offset=d.get("offset"),
            where_logic=d.get("where_logic", "AND"),
            having_logic=d.get("having_logic", "AND"),
            unwind=d.get("unwind"),
            include_id=d.get("include_id", True),
            match_patterns=[MatchPattern.from_dict(m) for m in d.get("match_patterns", [])],
            return_expressions=d.get("return_expressions", []),
        )
        return plan


def validate_plan_structure(plan: dict):
    """Validate that a raw dict has all required QueryPlan fields.

    Raises IRValidationError on structural issues.
    """
    required = {"action", "table", "columns"}
    missing = required - set(plan.keys())
    if missing:
        raise IRValidationError(f"Missing required fields: {missing}")

    action = plan.get("action", "").upper()
    if action not in ALLOWED_ACTIONS:
        raise IRValidationError(
            f"action must be one of {ALLOWED_ACTIONS}, got {action!r}"
        )

    db_type = plan.get("db_type", "sqlite")
    if db_type not in ALLOWED_DB_TYPES:
        raise IRValidationError(
            f"db_type must be one of {ALLOWED_DB_TYPES}, got {db_type!r}"
        )

    if not isinstance(plan.get("columns", []), list):
        raise IRValidationError("columns must be a list")
    if not isinstance(plan.get("joins", []), list):
        raise IRValidationError("joins must be a list")
    if not isinstance(plan.get("filters", []), list):
        raise IRValidationError("filters must be a list")

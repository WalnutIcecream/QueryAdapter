"""Neo4j Cypher constructor.

Translates the database-agnostic QueryPlan IR into a parameterized Cypher
query and executes it against a Neo4j database using the official driver.

Two construction paths are supported:

1. **Explicit graph IR** — when the plan carries ``match_patterns`` and
   ``return_expressions``, those are rendered directly.
2. **Relational fallback** — when only ``table``/``joins`` are present, a
   node pattern is built for ``table`` and each join becomes a relationship
   hop using the join target's label as the relationship type.
"""

from typing import Any, Optional


class ExecutionError(RuntimeError):
    """Raised when a generated Cypher query fails to execute."""


def _strip_table_prefix(col: str) -> str:
    if "." in col:
        return col.split(".", 1)[1]
    return col


def _direction_arrow(direction: str) -> str:
    d = direction.upper()
    if d == "INCOMING":
        return "<-"
    if d == "BOTH":
        return "-"
    return "->"


def _variable_length(min_hops: int, max_hops: int) -> str:
    if min_hops <= 1 and max_hops <= 1:
        return ""
    lo = max(min_hops, 1)
    hi = max_hops if max_hops >= lo else None
    if hi is None:
        return f"*{lo}.."
    if lo == hi:
        return f"*{lo}"
    return f"*{lo}..{hi}"


def _node_pattern(variable: str, labels: list[str], properties: dict) -> str:
    label_str = "".join(f":{label}" for label in labels)
    prop_str = ""
    if properties:
        pairs = ", ".join(f"{k}: ${k}" for k in sorted(properties))
        prop_str = f" {{{pairs}}}"
    return f"({variable}{label_str}{prop_str})"


class CypherBuilder:
    """Stateful Cypher query builder for a single plan."""

    def __init__(self, data: dict):
        self.data = data
        self.params: dict[str, Any] = {}
        self._param_counter = 0

    def _next_param(self, value: Any) -> str:
        name = f"p{self._param_counter}"
        self._param_counter += 1
        self.params[name] = value
        return f"${name}"

    def _where_condition(self, col: str, operator: str, value: Any) -> str:
        op = str(operator).upper()
        if op in ("IS", "IS NOT"):
            return f"{col} IS {'' if op == 'IS' else 'NOT '}NULL"
        if op == "BETWEEN":
            low, high = value if isinstance(value, (list, tuple)) else (value, value)
            return f"{col} >= {self._next_param(low)} AND {col} <= {self._next_param(high)}"
        if op in ("IN", "NOT IN"):
            values = value if isinstance(value, (list, tuple)) else [value]
            return f"{col} {op} {self._next_param(list(values))}"
        if op == "LIKE":
            return self._like_condition(col, value)
        if op in ("=", "!=", "<>", ">", "<", ">=", "<="):
            return f"{col} {op} {self._next_param(value)}"
        # Unknown operator: default to equality rather than injecting a symbol.
        return f"{col} = {self._next_param(value)}"

    def _like_condition(self, col: str, value: Any) -> str:
        text = str(value)
        if "%" in text or "_" in text:
            import re

            # SQL wildcards -> Cypher regex (escape everything except wildcards).
            parts = re.split(r"(%|_)", text)
            pattern_parts = []
            for part in parts:
                if part == "%":
                    pattern_parts.append(".*")
                elif part == "_":
                    pattern_parts.append(".")
                else:
                    pattern_parts.append(re.escape(part))
            regex = "(?i)" + "".join(pattern_parts)
            return f"{col} =~ {self._next_param(regex)}"
        return f"{col} CONTAINS {self._next_param(text)}"

    def _match_clauses(self) -> list[tuple[str, bool]]:
        """Return (clause, optional) pairs for every MATCH/OPTIONAL MATCH."""
        patterns = self.data.get("match_patterns", [])
        if patterns:
            return self._from_match_patterns(patterns)

        table = self.data.get("table", "")
        clauses: list[tuple[str, bool]] = []

        if table:
            clauses.append((f"MATCH ({'n'}:{table})", False))

        for idx, join in enumerate(self.data.get("joins", [])):
            target = join.get("table", "")
            if not target:
                continue
            jtype = str(join.get("type", "INNER")).upper()
            optional = jtype == "LEFT"
            rel_type = target.upper()
            from_var = "n" if idx == 0 else f"n{idx}"
            to_var = f"n{idx + 1}"
            arrow = _direction_arrow("OUTGOING")
            pattern = f"({from_var})-[{to_var}_rel:{rel_type}]{arrow}({to_var}:{target})"
            clauses.append((f"{'OPTIONAL ' if optional else ''}MATCH {pattern}", optional))

        return clauses

    def _from_match_patterns(self, patterns: list[dict]) -> list[tuple[str, bool]]:
        clauses: list[tuple[str, bool]] = []
        for mp in patterns:
            variable = mp.get("variable", "n")
            labels = mp.get("labels", [])
            rel_types = mp.get("relationship_types", [])
            optional = mp.get("optional", False)
            properties = mp.get("properties", {})

            if rel_types:
                rel = "|".join(f":{t}" for t in rel_types)
                length = _variable_length(int(mp.get("min_hops", 1)), int(mp.get("max_hops", 1)))
                arrow = _direction_arrow(mp.get("direction", "OUTGOING"))
                from_var = mp.get("from_variable")
                to_var = mp.get("to_variable")

                label_suffix = "".join(f":{l}" for l in labels)

                if from_var and to_var:
                    from_part = f"({from_var})"
                    to_part = f"({to_var}{label_suffix})"
                    pattern = f"{from_part}-[{variable}{rel}{length}]{arrow}{to_part}"
                elif from_var:
                    pattern = f"({from_var})-[{variable}{rel}{length}]{arrow}()"
                elif to_var:
                    pattern = f"()-[{variable}{rel}{length}]{arrow}({to_var}{label_suffix})"
                else:
                    pattern = f"()-[{variable}{rel}{length}]{arrow}()"
            else:
                pattern = _node_pattern(variable, labels, properties)

            clauses.append((f"{'OPTIONAL ' if optional else ''}MATCH {pattern}", optional))

        return clauses

    def _return_items(self) -> list[str]:
        """Build RETURN expressions, handling columns and aggregations."""
        items: list[str] = []

        return_exprs = self.data.get("return_expressions", [])
        if return_exprs:
            for entry in return_exprs:
                expr = entry.get("expression", entry.get("column", ""))
                alias = entry.get("alias", "")
                if expr and alias:
                    items.append(f"{expr} AS {alias}")
                elif expr:
                    items.append(expr)
            if not items:
                items.append("*")
            return items

        for col in self.data.get("columns", []):
            if col == "*":
                items.append("*")
            else:
                clean = _strip_table_prefix(col)
                items.append(clean)

        for agg in self.data.get("aggregations", []):
            func = str(agg.get("function", "COUNT")).upper()
            col = _strip_table_prefix(agg.get("column", "*"))
            expr = f"{func}({col})" if col != "*" else "COUNT(*)"
            alias = agg.get("alias") or f"{func.lower()}_{col.replace('.', '_')}"
            items.append(f"{expr} AS {alias}")

        if not items:
            items.append("*")

        return items

    def build(self) -> tuple[str, dict]:
        action = str(self.data.get("action", "SELECT")).upper()
        if action != "SELECT":
            raise ExecutionError(f"Only SELECT queries are allowed, got {action!r}")

        clauses: list[str] = []
        for clause, _ in self._match_clauses():
            clauses.append(clause)

        # WHERE on node/relationship properties
        filters = self.data.get("filters", [])
        if filters:
            conditions = [
                self._where_condition(f["column"], f.get("operator", "="), f.get("value"))
                for f in filters
            ]
            logic = str(self.data.get("where_logic", "AND")).upper()
            clauses.append(f"WHERE {(' ' + logic + ' ').join(conditions)}")

        has_group = bool(self.data.get("group_by") or self.data.get("aggregations"))
        having = self.data.get("having", [])
        group_by = self.data.get("group_by", [])

        if has_group and having:
            # Use WITH for HAVING: project group keys + aggregate aliases, filter, return.
            with_items = [_strip_table_prefix(g) for g in group_by]
            for agg in self.data.get("aggregations", []):
                func = str(agg.get("function", "COUNT")).upper()
                col = _strip_table_prefix(agg.get("column", "*"))
                alias = agg.get("alias") or f"{func.lower()}_{col.replace('.', '_')}"
                expr = f"{func}({col})" if col != "*" else "COUNT(*)"
                with_items.append(f"{expr} AS {alias}")
            if not with_items:
                with_items.append("*")
            clauses.append(f"WITH {', '.join(with_items)}")

            having_conditions = [
                self._where_condition(h["column"], h.get("operator", "="), h.get("value"))
                for h in having
            ]
            logic = str(self.data.get("having_logic", "AND")).upper()
            clauses.append(f"WHERE {(' ' + logic + ' ').join(having_conditions)}")

        # RETURN
        distinct = " DISTINCT" if self.data.get("distinct") else ""
        clauses.append(f"RETURN{distinct} {', '.join(self._return_items())}")

        # ORDER BY
        order_by = self.data.get("order_by", [])
        if order_by:
            parts = [
                f"{_strip_table_prefix(o['column'])} {o.get('direction', 'ASC')}"
                for o in order_by
            ]
            clauses.append(f"ORDER BY {', '.join(parts)}")

        if self.data.get("offset") is not None:
            clauses.append(f"SKIP {int(self.data['offset'])}")

        if self.data.get("limit") is not None:
            clauses.append(f"LIMIT {int(self.data['limit'])}")

        query = "\n".join(clauses)
        return query, self.params


def build_cypher(data: dict) -> tuple[str, dict]:
    """Build a parameterized Cypher query string from a normalized plan.

    Returns ``(query, params)``.
    """
    return CypherBuilder(data).build()


def build_and_execute_cypher(
    data: dict,
    connection_string: str,
    username: str = "",
    password: str = "",
) -> tuple[str, dict, list]:
    """Build a Cypher query and execute it against Neo4j.

    Returns ``(query, params, records)``. Records preserve graph-specific
    structure: each record is a dict of ``{key: value}`` where values may be
    Neo4j ``Node``/``Relationship`` objects.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ExecutionError(
            "neo4j driver is required for Neo4j support. "
            "Install with: pip install queryadapter[neo4j]"
        ) from exc

    query, params = build_cypher(data)

    auth = (username, password) if username and password else None
    driver = GraphDatabase.driver(connection_string, auth=auth)
    try:
        with driver.session() as session:
            result = session.run(query, **params)
            records = []
            for record in result:
                records.append(dict(record))
    except Exception as exc:
        raise ExecutionError(f"Neo4j query failed: {exc}") from exc
    finally:
        driver.close()

    return query, params, records

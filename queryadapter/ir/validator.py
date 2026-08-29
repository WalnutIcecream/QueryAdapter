import re

IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
DOTTED_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*$')

ALLOWED_AGG_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
ALLOWED_OPERATORS = {"=", "!=", "<>", ">", "<", ">=", "<=", "LIKE", "IN", "NOT IN", "IS", "IS NOT", "BETWEEN"}
ALLOWED_ACTIONS = {"SELECT"}


class SchemaValidationError(ValueError):
    """Raised when a query plan violates schema or security constraints."""
    pass


def _validate_identifier(label, identifier):
    if identifier == "*":
        return
    if "." in identifier:
        if not DOTTED_IDENTIFIER_PATTERN.match(identifier):
            raise SchemaValidationError(
                f"Invalid {label} identifier {identifier!r}"
            )
        return
    if not IDENTIFIER_PATTERN.match(identifier):
        raise SchemaValidationError(
            f"Invalid {label} identifier {identifier!r}"
        )


def _validate_graph_plan(data, tables):
    """Validate a Neo4j graph plan (match_patterns) against discovered labels.

    ``tables`` keys are node labels (e.g. ``"Customer"``) or relationship
    types (``":PLACED"``). Label existence is checked against the discovered
    schema; operators and aggregates are whitelisted identically to SQL.
    """
    known_labels = {k for k in tables.keys() if not k.startswith(":")}
    known_rel_types = {k.lstrip(":") for k in tables.keys() if k.startswith(":")}

    for mp in data.get("match_patterns", []):
        for label in mp.get("labels", []):
            if known_labels and label not in known_labels:
                raise SchemaValidationError(
                    f"Node label {label!r} not found. Available: {sorted(known_labels)}"
                )
        for rel_type in mp.get("relationship_types", []):
            if known_rel_types and rel_type not in known_rel_types:
                raise SchemaValidationError(
                    f"Relationship type {rel_type!r} not found. "
                    f"Available: {sorted(known_rel_types)}"
                )

    for f in data.get("filters", []):
        op = str(f.get("operator", "")).upper()
        if op and op not in ALLOWED_OPERATORS:
            raise SchemaValidationError(
                f"Disallowed operator {f.get('operator')!r}. Allowed: {sorted(ALLOWED_OPERATORS)}"
            )

    for a in data.get("aggregations", []):
        func = str(a.get("function", "")).upper()
        if func and func not in ALLOWED_AGG_FUNCTIONS:
            raise SchemaValidationError(
                f"Disallowed aggregate function {a.get('function')!r}. "
                f"Allowed: {sorted(ALLOWED_AGG_FUNCTIONS)}"
            )

    for field in ("where_logic", "having_logic"):
        val = str(data.get(field, "AND")).upper()
        data[field] = val if val in ("AND", "OR") else "AND"

    for field in ("limit", "offset"):
        val = data.get(field)
        if val is not None and (not isinstance(val, int) or val < 0):
            raise SchemaValidationError(
                f"{field} must be a non-negative integer or null, got {val!r}"
            )

    return data


def validate_against_schema(data, tables):
    """Validate a normalized query plan against the actual database schema.

    Raises SchemaValidationError with a descriptive message on any violation.
    Returns the (possibly sanitized) data dict on success.
    """
    # 1. Action must be SELECT only
    action = data.get("action", "").upper()
    if action not in ALLOWED_ACTIONS:
        raise SchemaValidationError(
            f"Only SELECT queries are allowed, got {action!r}"
        )

    if data.get("db_type") == "neo4j" and data.get("match_patterns"):
        return _validate_graph_plan(data, tables)

    # 2. Main table must exist and have a valid name
    main_table = data.get("table", "")
    if not main_table:
        raise SchemaValidationError("No table specified in query plan")
    _validate_identifier("table name", main_table)
    if main_table not in tables:
        raise SchemaValidationError(
            f"Table {main_table!r} does not exist. Available: {sorted(tables.keys())}"
        )

    # 3. Join tables must exist
    visible_cols = set(tables.get(main_table, set()))
    for join in data.get("joins", []):
        jt = join.get("table", "")
        _validate_identifier("join table", jt)
        if jt not in tables:
            raise SchemaValidationError(
                f"Join table {jt!r} does not exist. Available: {sorted(tables.keys())}"
            )
        visible_cols.update(tables.get(jt, set()))

    def _check_column(label, col):
        if not col or col == "*":
            return
        bare = col.split(".")[-1]
        if bare not in visible_cols:
            raise SchemaValidationError(
                f"{label} column {col!r} not found. Available: {sorted(visible_cols)}"
            )

    # 4. Validate SELECT columns
    for col in data.get("columns", []):
        _validate_identifier("column", col)
        _check_column("SELECT", col)

    # 5. Validate filters
    for f in data.get("filters", []):
        col = f.get("column", "")
        _validate_identifier("filter column", col)
        _check_column("Filter", col)
        op = str(f.get("operator", "")).upper()
        if op and op not in ALLOWED_OPERATORS:
            raise SchemaValidationError(
                f"Disallowed operator {f.get('operator')!r}. Allowed: {sorted(ALLOWED_OPERATORS)}"
            )

    # 6. Validate aggregations
    for a in data.get("aggregations", []):
        col = a.get("column", "")
        if col != "*":
            _validate_identifier("aggregation column", col)
            _check_column("Aggregation", col)
        func = str(a.get("function", "")).upper()
        if func and func not in ALLOWED_AGG_FUNCTIONS:
            raise SchemaValidationError(
                f"Disallowed aggregate function {a.get('function')!r}. Allowed: {sorted(ALLOWED_AGG_FUNCTIONS)}"
            )

    # 7. Validate GROUP BY
    for col in data.get("group_by", []):
        _validate_identifier("GROUP BY column", col)
        _check_column("GROUP BY", col)

    # 8. Validate ORDER BY
    aggregate_aliases = {a.get("alias", "") for a in data.get("aggregations", []) if a.get("alias")}
    for o in data.get("order_by", []):
        col = o.get("column", "")
        _validate_identifier("ORDER BY column", col)
        # Allow aggregate aliases (computed columns not in the schema)
        if col not in aggregate_aliases:
            _check_column("ORDER BY", col)

    # 9. Validate HAVING
    for h in data.get("having", []):
        col = h.get("column", "")
        if col != "*":
            _validate_identifier("HAVING column", col)
            _check_column("HAVING", col)
        op = str(h.get("operator", "")).upper()
        if op and op not in ALLOWED_OPERATORS:
            raise SchemaValidationError(
                f"Disallowed operator {h.get('operator')!r} in HAVING. Allowed: {sorted(ALLOWED_OPERATORS)}"
            )

    # 10. Validate join ON columns
    for join in data.get("joins", []):
        for left, right in join.get("on", {}).items():
            _validate_identifier("join ON column", left)
            _validate_identifier("join ON column", right)
            _check_column("Join ON", left)
            _check_column("Join ON", right)

    # 11. Sanitize where_logic / having_logic
    for field in ("where_logic", "having_logic"):
        val = str(data.get(field, "AND")).upper()
        if val not in ("AND", "OR"):
            data[field] = "AND"
        else:
            data[field] = val

    # 12. Validate limit/offset
    for field in ("limit", "offset"):
        val = data.get(field)
        if val is not None:
            if not isinstance(val, int) or val < 0:
                raise SchemaValidationError(
                    f"{field} must be a non-negative integer or null, got {val!r}"
                )

    return data

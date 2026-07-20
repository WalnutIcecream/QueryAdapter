import sqlite3


def _build_filter_clause(filters, logic="AND"):
    """Build WHERE/HAVING parameterized clauses from filter dicts.

    Returns (sql_string, params_list).
    """
    if not filters:
        return "", []

    parts = []
    params = []

    for f in filters:
        col = f["column"]
        op = str(f.get("operator", "=")).upper()
        val = f.get("value")

        if op in ("IS", "IS NOT"):
            parts.append(f"{col} {op} NULL")
            # No parameter for IS NULL / IS NOT NULL
        elif op == "BETWEEN":
            parts.append(f"{col} BETWEEN ? AND ?")
            if isinstance(val, (list, tuple)) and len(val) == 2:
                params.extend(val)
            else:
                params.extend([val, val])
        elif op in ("IN", "NOT IN"):
            if not isinstance(val, (list, tuple)):
                val = [val]
            placeholders = ", ".join(["?"] * len(val))
            parts.append(f"{col} {op} ({placeholders})")
            params.extend(val)
        else:
            # Standard comparison: =, !=, <, >, <=, >=, LIKE, etc.
            parts.append(f"{col} {op} ?")
            params.append(val)

    clause = f" {logic} ".join(parts)
    return clause, params


def build_and_execute(data, db_path):
    """Build a parameterized SQL query from a normalized query plan and execute it.

    Raises ValueError if the action is not SELECT.
    Returns (query_string, params_list, result_rows).
    """
    action = data.get("action", "").upper()
    if action != "SELECT":
        raise ValueError(f"Only SELECT queries are allowed, got {action!r}")

    params = []
    query_parts = []

    # SELECT clause
    select_items = list(data.get("columns", [])) or ["*"]
    for agg in data.get("aggregations", []):
        expr = f"{agg['function']}({agg['column']})"
        if agg.get("alias"):
            expr += f" AS {agg['alias']}"
        select_items.append(expr)

    select_clause = "SELECT"
    if data.get("distinct"):
        select_clause += " DISTINCT"
    select_clause += " " + ", ".join(select_items)
    query_parts.append(select_clause)

    # FROM clause
    query_parts.append(f"FROM {data['table']}")

    # JOIN clauses
    for join in data.get("joins", []):
        on_parts = [f"{l} = {r}" for l, r in join["on"].items()]
        query_parts.append(
            f"{join.get('type', 'INNER')} JOIN {join['table']} "
            f"ON {' AND '.join(on_parts)}"
        )

    # WHERE clause
    where_sql, where_params = _build_filter_clause(
        data.get("filters", []),
        data.get("where_logic", "AND"),
    )
    if where_sql:
        query_parts.append(f"WHERE {where_sql}")
        params.extend(where_params)

    # GROUP BY clause
    if data.get("group_by"):
        query_parts.append("GROUP BY " + ", ".join(data["group_by"]))

    # HAVING clause
    having_sql, having_params = _build_filter_clause(
        data.get("having", []),
        data.get("having_logic", "AND"),
    )
    if having_sql:
        query_parts.append(f"HAVING {having_sql}")
        params.extend(having_params)

    # ORDER BY clause
    if data.get("order_by"):
        order_parts = []
        for o in data["order_by"]:
            order_parts.append(f"{o['column']} {o.get('direction', 'ASC')}")
        query_parts.append("ORDER BY " + ", ".join(order_parts))

    # LIMIT clause
    if data.get("limit") is not None:
        query_parts.append("LIMIT ?")
        params.append(data["limit"])

    # OFFSET clause
    if data.get("offset") is not None:
        query_parts.append("OFFSET ?")
        params.append(data["offset"])

    query = " ".join(query_parts)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return query, params, rows

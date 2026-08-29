"""MongoDB MQL aggregation pipeline constructor (queryadapter.backends.mongodb).

Converts a normalized query plan (the common JSON IR) into a MongoDB
aggregation pipeline and executes it against a MongoDB database.

Connection string format: mongodb://host:port/database
"""

import json


MQL_OPERATOR_MAP = {
    "=": "$eq",
    "!=": "$ne",
    "<>": "$ne",
    ">": "$gt",
    "<": "$lt",
    ">=": "$gte",
    "<=": "$lte",
    "IN": "$in",
    "NOT IN": "$nin",
}

AGGREGATE_MAP = {
    "COUNT": "$sum",
    "SUM": "$sum",
    "AVG": "$avg",
    "MIN": "$min",
    "MAX": "$max",
}


def _strip_table_prefix(col):
    """Remove table prefix: 'employees.name' → 'name'."""
    if "." in col:
        return col.split(".", 1)[1]
    return col


def _build_match_clause(filters, logic="AND"):
    """Convert filter list to a $match stage document."""
    if not filters:
        return None

    conditions = []
    for f in filters:
        col = _strip_table_prefix(f["column"])
        op = str(f.get("operator", "=")).upper()
        val = f.get("value")

        if op in ("IS", "IS NOT"):
            mql_op = "$eq" if op == "IS" else "$ne"
            conditions.append({col: {mql_op: None}})
        elif op == "BETWEEN":
            low, high = val if isinstance(val, (list, tuple)) else (val, val)
            conditions.append({col: {"$gte": low, "$lte": high}})
        elif op in ("IN", "NOT IN"):
            mql_op = "$in" if op == "IN" else "$nin"
            conditions.append({col: {mql_op: val if isinstance(val, list) else [val]}})
        elif op == "LIKE":
            escaped = str(val).replace("%", ".*").replace("_", ".").replace("?", ".")
            conditions.append({col: {"$regex": f"^{escaped}$", "$options": "i"}})
        elif op in MQL_OPERATOR_MAP:
            conditions.append({col: {MQL_OPERATOR_MAP[op]: val}})
        else:
            conditions.append({col: {"$eq": val}})

    if logic == "OR":
        return {"$match": {"$or": conditions}}
    elif len(conditions) == 1:
        return {"$match": conditions[0]}
    else:
        return {"$match": {"$and": conditions}}


def _build_lookup_stages(joins, main_table):
    """Convert JOINs to $lookup + $unwind stages."""
    stages = []
    for join in joins:
        jtype = join.get("type", "INNER").upper()
        target = join["table"]
        on = join.get("on", {})

        local_field = None
        foreign_field = None
        for left, right in on.items():
            local = _strip_table_prefix(left)
            foreign = _strip_table_prefix(right)
            if not local_field:
                local_field = local
                foreign_field = foreign

        if not local_field:
            continue

        alias = target
        stage = {
            "$lookup": {
                "from": target,
                "localField": local_field,
                "foreignField": foreign_field,
                "as": alias,
            }
        }
        stages.append(stage)

        # $unwind the looked-up array
        unwind_stage = {"$unwind": {"path": f"${alias}", "preserveNullAndEmptyArrays": jtype == "LEFT"}}
        stages.append(unwind_stage)

    return stages


def _build_group_stage(group_by, aggregations):
    """Build $group stage from GROUP BY and aggregation fields."""
    if not group_by and not aggregations:
        return None

    group_doc = {}

    # Build _id from GROUP BY keys
    if group_by:
        clean_keys = [_strip_table_prefix(k) for k in group_by]
        if len(clean_keys) == 1:
            group_doc["_id"] = f"${clean_keys[0]}"
        else:
            id_parts = {k: f"${k}" for k in clean_keys}
            group_doc["_id"] = id_parts
    else:
        group_doc["_id"] = None

    # Add accumulator expressions
    for agg in aggregations:
        func = str(agg.get("function", "COUNT")).upper()
        col = _strip_table_prefix(agg.get("column", "*"))
        alias = agg.get("alias") or f"{func.lower()}_{col.replace('.', '_')}"

        mql_acc = AGGREGATE_MAP.get(func, "$sum")
        if func == "COUNT" and col == "*":
            group_doc[alias] = {"$sum": 1}
        elif func == "COUNT":
            group_doc[alias] = {"$sum": {"$cond": [{"$ne": [f"${col}", None]}, 1, 0]}}
        else:
            group_doc[alias] = {mql_acc: f"${col}"}

    return {"$group": group_doc}


def _build_project_stage(columns, aggregations, has_group, include_id):
    """Build $project stage for column selection and _id suppression."""
    if not columns and not aggregations:
        if not include_id:
            return None
        return None

    projection = {}

    if has_group:
        # After $group, promote _id fields back to top-level
        for col in columns:
            clean = _strip_table_prefix(col)
            if clean == "*":
                projection["_id"] = 0
            else:
                projection[clean] = f"$_id.{clean}" if isinstance(aggregations, list) and any(a.get("column") != "*" for a in aggregations) else f"$_id"

        # Include accumulator aliases
        for agg in aggregations:
            alias = agg.get("alias") or f"{agg.get('function', '').lower()}_{_strip_table_prefix(agg.get('column', '*'))}"
            projection[alias] = 1

        if "_id" not in projection:
            projection["_id"] = 1 if include_id else 0
    else:
        # No grouping: project individual fields
        for col in columns:
            clean = _strip_table_prefix(col)
            if clean == "*":
                continue
            projection[clean] = 1

        if not include_id:
            projection["_id"] = 0

    if not projection:
        return None

    return {"$project": projection}


def _build_sort_stage(order_by):
    """Build $sort stage from ORDER BY fields."""
    if not order_by:
        return None

    sort_doc = {}
    for o in order_by:
        col = _strip_table_prefix(o.get("column", ""))
        direction = 1 if o.get("direction", "ASC").upper() == "ASC" else -1
        sort_doc[col] = direction

    return {"$sort": sort_doc}


def _build_distinct_stage(distinct, columns):
    """Build $group stage for DISTINCT semantics."""
    if not distinct or not columns:
        return None

    clean_cols = [_strip_table_prefix(c) for c in columns if c != "*"]
    if not clean_cols:
        return None

    if len(clean_cols) == 1:
        id_expr = f"${clean_cols[0]}"
    else:
        id_expr = {c: f"${c}" for c in clean_cols}

    group = {"$group": {"_id": id_expr}}
    replace = {"$replaceRoot": {"newRoot": "$_id"}}
    return [group, replace]


def build_mql_pipeline(data):
    """Build a MongoDB aggregation pipeline from a normalized query plan.

    Args:
        data: Normalized query plan dict.

    Returns:
        list: MongoDB aggregation pipeline stages (list of dicts).
    """
    if data.get("action", "").upper() != "SELECT":
        raise ValueError(f"Only SELECT queries are allowed, got {data['action']!r}")

    main_collection = data["table"]
    pipeline = []

    # Stage 1: $match (WHERE filters)
    match = _build_match_clause(data.get("filters", []), data.get("where_logic", "AND"))
    if match:
        pipeline.append(match)

    # Stage 2: $lookup + $unwind (JOINs)
    lookups = _build_lookup_stages(data.get("joins", []), main_collection)
    pipeline.extend(lookups)

    # Stage 3: $unwind (explicit array unwinding, MongoDB-specific)
    if data.get("unwind"):
        unwind_opts = {"path": f"${data['unwind']}"}
        pipeline.append({"$unwind": unwind_opts})

    has_group = bool(data.get("group_by") or data.get("aggregations"))

    # Stage 4a: $group (GROUP BY + aggregations)
    group = _build_group_stage(data.get("group_by", []), data.get("aggregations", []))
    if group:
        pipeline.append(group)

    # Stage 4b: DISTINCT (via group + replaceRoot)
    if data.get("distinct") and not has_group:
        distinct = _build_distinct_stage(data.get("distinct"), data.get("columns", []))
        if distinct:
            pipeline.extend(distinct)

    # Stage 5: post-group $match (HAVING)
    having = _build_match_clause(data.get("having", []), data.get("having_logic", "AND"))
    if having:
        pipeline.append(having)

    # Stage 6: $project (SELECT columns)
    proj = _build_project_stage(
        data.get("columns", []),
        data.get("aggregations", []),
        has_group,
        data.get("include_id", True),
    )
    if proj:
        pipeline.append(proj)

    # Stage 7: $sort (ORDER BY)
    sort = _build_sort_stage(data.get("order_by", []))
    if sort:
        pipeline.append(sort)

    # Stage 8: $skip (OFFSET)
    if data.get("offset") is not None:
        pipeline.append({"$skip": data["offset"]})

    # Stage 9: $limit (LIMIT)
    if data.get("limit") is not None:
        pipeline.append({"$limit": data["limit"]})

    return pipeline


def build_and_execute_mql(data, connection_string):
    """Build a MongoDB aggregation pipeline and execute it.

    Args:
        data: Normalized query plan dict.
        connection_string: MongoDB URI (mongodb://host:port/database).

    Returns:
        tuple: (pipeline_list, result_docs_list)
    """
    try:
        from pymongo import MongoClient
    except ImportError:
        raise ImportError(
            "pymongo is required for MongoDB support. Install it with: pip install pymongo"
        )

    pipeline = build_mql_pipeline(data)

    db_name = connection_string.rsplit("/", 1)[-1]
    client = MongoClient(connection_string)
    db = client[db_name]
    collection = db[data["table"]]

    cursor = collection.aggregate(pipeline)
    results = list(cursor)
    client.close()

    return pipeline, results

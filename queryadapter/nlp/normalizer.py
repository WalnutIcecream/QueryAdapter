import json
import re

from queryadapter.ir.validator import validate_against_schema, SchemaValidationError
from queryadapter.backends.discovery import get_discovery, BackendDiscovery


def strip_json(s):
    s = s.strip()
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return s.strip()


def sanitize_json(s):
    s = re.sub(r",\s*([}\]])", r"\1", s)
    depth = 0
    out = []
    for ch in s:
        if ch in ("{", "["):
            depth += 1
            out.append(ch)
        elif ch in ("}", "]"):
            if depth > 0:
                depth -= 1
                out.append(ch)
        else:
            out.append(ch)
    while depth > 0:
        out.append("}" if depth <= 2 else "]")
        depth -= 1
    return "".join(out)


def _resolve_discovery(db_path_or_discovery, db_type="sqlite", **kwargs):
    """Resolve a db_path string or BackendDiscovery object."""
    from queryadapter.backends.discovery import BackendDiscovery
    if isinstance(db_path_or_discovery, BackendDiscovery):
        return db_path_or_discovery
    return get_discovery(db_type, db_path_or_discovery, **kwargs)


def get_schema(db_path_or_discovery, db_type="sqlite"):
    """Return {table_name: {column_name, ...}} by reading the live database."""
    discovery = _resolve_discovery(db_path_or_discovery, db_type)
    return discovery.get_collections()


def get_schema_ddl(db_path_or_discovery, db_type="sqlite"):
    """Return schema DDL text for the NLP model."""
    discovery = _resolve_discovery(db_path_or_discovery, db_type)
    return discovery.get_ddl()


EXPR_PATTERN = re.compile(
    r"(.+?)\s*(>=|<=|!=|<>|=|>|<)\s*(.+)", re.IGNORECASE
)
EXPR_PATTERN_WORD = re.compile(
    r"(.+?)\s+((?:NOT\s+)?IN|IS\s+NOT|IS|LIKE)\s+(.+)", re.IGNORECASE
)
EXPR_PATTERN_BETWEEN = re.compile(
    r"(.+?)\s+BETWEEN\s+(.+?)\s+AND\s+(.+)", re.IGNORECASE
)
AGG_PATTERN = re.compile(
    r"(COUNT|SUM|AVG|MIN|MAX|COUNT DISTINCT)\s*\(\s*(.+?)\s*\)"
    r"(?:\s+AS\s+(.+))?$",
    re.IGNORECASE,
)

COL_KEY_ALIASES = ("column", "name", "field", "col", "attribute")
OP_KEY_ALIASES = ("operator", "op", "condition", "condition_type")

CONDITION_TYPE_MAP = {
    "greater_than": ">", "less_than": "<", "equals": "=",
    "not_equals": "!=", "greater_than_or_equal": ">=",
    "less_than_or_equal": "<=", "like": "LIKE", "in": "IN",
    "not_in": "NOT IN", "is_null": "IS", "is_not_null": "IS NOT",
    "gt": ">", "lt": "<", "eq": "=", "neq": "!=", "ne": "!=",
    "gte": ">=", "ge": ">=", "lte": "<=", "le": "<=",
    "between": "BETWEEN",
}

FUNC_KEY_ALIASES = ("function", "type", "func", "agg_type", "aggregation")

NULL_VALUES = {"null", "none", "nil"}


def first_key(d, keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def extract_name(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        candidates = ("name", "column", "field", "value", "key")
        return first_key(item, candidates) or next(iter(item.values()), "")
    return str(item)


def extract_string_list(items):
    if not items:
        return []
    return [extract_name(i) for i in items]


def extract_aggregations_from_columns(columns):
    aggs = []
    clean = []
    for col in columns:
        m = AGG_PATTERN.match(col.strip())
        if m:
            entry = {"function": m.group(1).upper(), "column": m.group(2).strip()}
            if m.group(3):
                entry["alias"] = m.group(3).strip()
            aggs.append(entry)
        else:
            clean.append(col)
    return clean, aggs


def _parse_value(raw):
    """Convert a raw value string to the best Python type."""
    if not isinstance(raw, str):
        return raw
    raw = raw.strip()
    low = raw.lower()
    if low in NULL_VALUES:
        return None
    if (raw.startswith("'") and raw.endswith("'")) or \
       (raw.startswith('"') and raw.endswith('"')):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def _parse_in_list(raw):
    """Parse (1, 2, 'abc') or [1, 2, 'abc'] into a list of Python values."""
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    elif raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    result = []
    for piece in raw.split(","):
        piece = piece.strip()
        if piece:
            result.append(_parse_value(piece))
    return result


def parse_expr(s):
    if not isinstance(s, str):
        return None
    s = s.strip()

    # BETWEEN
    m = EXPR_PATTERN_BETWEEN.match(s)
    if m:
        return {
            "column": m.group(1).strip(),
            "operator": "BETWEEN",
            "value": [_parse_value(m.group(2)), _parse_value(m.group(3))],
        }

    # Standard comparison: =, !=, <, >, <=, >=
    m = EXPR_PATTERN.match(s)
    if m:
        return {
            "column": m.group(1).strip(),
            "operator": m.group(2).upper(),
            "value": _parse_value(m.group(3)),
        }

    # Word operators: LIKE, IN, NOT IN, IS, IS NOT
    m = EXPR_PATTERN_WORD.match(s)
    if m:
        col = m.group(1).strip()
        op = m.group(2).upper()
        val = m.group(3).strip()
        if op in ("IN", "NOT IN"):
            return {"column": col, "operator": op, "value": _parse_in_list(val)}
        if op in ("IS", "IS NOT"):
            if val.lower() in NULL_VALUES:
                return {"column": col, "operator": op, "value": None}
            return {"column": col, "operator": op, "value": _parse_value(val)}
        return {"column": col, "operator": op, "value": _parse_value(val)}

    return None


def normalize_filters(filters):
    result = []
    for f in filters:
        if isinstance(f, str):
            parsed = parse_expr(f)
            if parsed:
                result.append(parsed)
            continue
        if not isinstance(f, dict):
            continue

        col = first_key(f, COL_KEY_ALIASES)
        op = first_key(f, OP_KEY_ALIASES)
        val = f.get("value")

        if op and str(op).lower() in CONDITION_TYPE_MAP:
            op = CONDITION_TYPE_MAP[str(op).lower()]

        # Handle IS NULL / IS NOT NULL
        if op in ("IS", "IS NOT"):
            if val is None or (isinstance(val, str) and val.lower() in NULL_VALUES):
                result.append({"column": col, "operator": op, "value": None})
                continue

        # Handle BETWEEN
        if op == "BETWEEN":
            if isinstance(val, (list, tuple)) and len(val) == 2:
                result.append({"column": col, "operator": "BETWEEN", "value": list(val)})
            elif isinstance(val, str):
                parsed = parse_expr(val)
                if parsed:
                    result.append(parsed)
            continue

        # Handle IN / NOT IN
        if op in ("IN", "NOT IN"):
            if isinstance(val, (list, tuple)):
                result.append({"column": col, "operator": op, "value": list(val)})
            elif isinstance(val, str):
                result.append({"column": col, "operator": op, "value": _parse_in_list(val)})
            continue

        if col and op is not None:
            if op not in ("BETWEEN", "IN", "NOT IN"):
                val = _parse_value(val) if isinstance(val, str) else val
            result.append({"column": col, "operator": op, "value": val})
        elif f.get("condition") and isinstance(f["condition"], str):
            parsed = parse_expr(f["condition"])
            if parsed:
                result.append(parsed)
        elif f.get("expression") and isinstance(f["expression"], str):
            parsed = parse_expr(f["expression"])
            if parsed:
                result.append(parsed)

    return result


def normalize_aggregations(aggs):
    if not aggs:
        return []
    result = []
    for a in aggs:
        if isinstance(a, str):
            m = re.match(r"(\w+)\((.+?)\)(?:\s+AS\s+(.+))?$", a, re.IGNORECASE)
            if m:
                entry = {"function": m.group(1).upper(), "column": m.group(2).strip()}
                if m.group(3):
                    entry["alias"] = m.group(3).strip()
                result.append(entry)
            continue
        if not isinstance(a, dict):
            continue

        col = first_key(a, COL_KEY_ALIASES)
        func = first_key(a, FUNC_KEY_ALIASES)

        if col:
            m = AGG_PATTERN.match(col.strip())
            if m:
                entry = {"function": m.group(1).upper(), "column": m.group(2).strip()}
                if m.group(3):
                    entry["alias"] = m.group(3).strip()
                if func:
                    entry["function"] = func.upper()
                result.append(entry)
                continue
            entry = {"function": (func or "COUNT").upper(), "column": col}
            if a.get("alias"):
                entry["alias"] = a["alias"]
            result.append(entry)
        elif "columns" in a:
            c = extract_name(a["columns"][0]) if a["columns"] else "1"
            entry = {"function": (func or "COUNT").upper(), "column": c}
            result.append(entry)
        elif "expression" in a and isinstance(a["expression"], str):
            m = AGG_PATTERN.match(a["expression"])
            if m:
                entry = {"function": m.group(1).upper(), "column": m.group(2).strip()}
                if m.group(3):
                    entry["alias"] = m.group(3).strip()
                result.append(entry)
    return result


def normalize_having(having):
    if not having:
        return []
    result = []
    for h in having:
        if isinstance(h, str):
            parsed = parse_expr(h)
            if parsed:
                result.append(parsed)
            continue
        if not isinstance(h, dict):
            continue

        col = first_key(h, COL_KEY_ALIASES)
        func = first_key(h, FUNC_KEY_ALIASES)
        op = first_key(h, OP_KEY_ALIASES)

        if col and op is not None:
            val = h.get("value")
            if str(op).lower() in CONDITION_TYPE_MAP:
                op = CONDITION_TYPE_MAP[str(op).lower()]
            entry = {"column": col, "operator": op, "value": val}
            if func:
                entry["function"] = func.upper()
            if op in ("IS", "IS NOT") and (val is None or (isinstance(val, str) and val.lower() in NULL_VALUES)):
                entry["value"] = None
            result.append(entry)
        elif op is not None and h.get("expression"):
            parsed = parse_expr(h["expression"])
            if parsed:
                result.append(parsed)
        elif h.get("expression"):
            m = AGG_PATTERN.match(h["expression"])
            if m:
                result.append({
                    "function": m.group(1).upper(),
                    "column": m.group(2).strip(),
                    "operator": ">",
                    "value": 0,
                })
            else:
                parsed = parse_expr(h["expression"])
                if parsed:
                    result.append(parsed)
        elif func and col:
            result.append({
                "function": func.upper(),
                "column": col,
                "operator": ">",
                "value": 0,
            })

    return result


def normalize_order_by(order_by):
    result = []
    for item in order_by:
        if isinstance(item, (list, tuple)) and len(item) >= 1:
            col = extract_name(item[0])
            direction = str(item[1]).upper() if len(item) > 1 else "ASC"
            if direction not in ("ASC", "DESC"):
                direction = "ASC"
            result.append({"column": col, "direction": direction})
        elif isinstance(item, dict):
            col = extract_name(item)
            result.append({
                "column": col,
                "direction": item.get("direction", "ASC"),
            })
        elif isinstance(item, str):
            m = re.match(r"(.+?)\s+(ASC|DESC)$", item, re.IGNORECASE)
            if m:
                result.append({
                    "column": m.group(1).strip(),
                    "direction": m.group(2).upper(),
                })
            else:
                result.append({"column": item.strip(), "direction": "ASC"})
    return result


def infer_join_condition(main_table, join_table, discovery):
    """Infer join conditions using the backend discovery adapter."""
    return discovery.infer_relationships(main_table, join_table)


def normalize_joins(joins, main_table, discovery):
    result = []
    for j in joins:
        if isinstance(j, dict):
            j = dict(j)
            if "join_type" in j and "type" not in j:
                j["type"] = j.pop("join_type").replace(" JOIN", "")
            j.setdefault("type", "INNER")
            if isinstance(j.get("on"), str):
                inferred = infer_join_condition(main_table, j["table"], discovery)
                if inferred:
                    j["on"] = inferred
                else:
                    parsed = parse_expr(j["on"])
                    if parsed:
                        left = parsed["column"]
                        right = str(parsed["value"])
                        j["on"] = {left: right}
            if "on" not in j or not j["on"]:
                j["on"] = infer_join_condition(main_table, j["table"], discovery)
            result.append(j)
        elif isinstance(j, str):
            on_clause = infer_join_condition(main_table, j, discovery)
            result.append({"type": "INNER", "table": j, "on": on_clause})
    return result


def infer_missing_joins(data, tables, discovery):
    main_table = data.get("table", "")
    existing_joins = {j["table"] for j in data.get("joins", [])}
    referenced_tables = set()

    def find_table_for_column(col):
        col = col.strip()
        if "." in col:
            t = col.split(".")[0]
            return t if t in tables else None
        if main_table in tables and col in tables[main_table]:
            return main_table
        for tname, tcols in tables.items():
            if col in tcols:
                return tname
        return None

    for col in data.get("columns", []):
        t = find_table_for_column(col)
        if t and t != main_table:
            referenced_tables.add(t)

    for f in data.get("filters", []):
        if isinstance(f, dict):
            t = find_table_for_column(f.get("column", ""))
            if t and t != main_table:
                referenced_tables.add(t)

    for agg in data.get("aggregations", []):
        if isinstance(agg, dict):
            t = find_table_for_column(agg.get("column", ""))
            if t and t != main_table:
                referenced_tables.add(t)

    for col in data.get("group_by", []):
        t = find_table_for_column(col)
        if t and t != main_table:
            referenced_tables.add(t)

    for o in data.get("order_by", []):
        if isinstance(o, dict):
            t = find_table_for_column(o.get("column", ""))
            if t and t != main_table:
                referenced_tables.add(t)

    new_joins = list(data.get("joins", []))
    for t in referenced_tables:
        if t not in existing_joins:
            on_clause = infer_join_condition(main_table, t, discovery)
            if on_clause:
                new_joins.append({"type": "INNER", "table": t, "on": on_clause})

    return new_joins


def qualify_columns(data, tables):
    main_table = data.get("table", "")
    joined = {j["table"] for j in data.get("joins", [])}
    if not joined:
        return data

    def qualify(col):
        if "." in col:
            return col
        found_in = [t for t in [main_table] + list(joined) if col in tables.get(t, set())]
        if len(found_in) == 1:
            return f"{found_in[0]}.{col}"
        if len(found_in) > 1:
            return f"{main_table}.{col}"
        return col

    data["columns"] = [qualify(c) for c in data.get("columns", [])]
    data["group_by"] = [qualify(c) for c in data.get("group_by", [])]
    for f in data.get("filters", []):
        f["column"] = qualify(f.get("column", ""))
    for o in data.get("order_by", []):
        o["column"] = qualify(o.get("column", ""))
    for a in data.get("aggregations", []):
        a["column"] = qualify(a.get("column", ""))
    for h in data.get("having", []):
        h["column"] = qualify(h.get("column", ""))

    return data


def _normalize_match_patterns(patterns):
    """Normalize Neo4j match_patterns entries into canonical dicts."""
    if not patterns:
        return []
    result = []
    for mp in patterns:
        if isinstance(mp, str):
            result.append({"variable": mp})
            continue
        if not isinstance(mp, dict):
            continue

        normalized = {
            "variable": mp.get("variable", "n"),
            "labels": mp.get("labels", []),
            "relationship_types": mp.get("relationship_types", mp.get("relationships", [])),
            "direction": str(mp.get("direction", "OUTGOING")).upper(),
            "min_hops": mp.get("min_hops", 1),
            "max_hops": mp.get("max_hops", mp.get("min_hops", 1)),
            "optional": mp.get("optional", False),
            "properties": mp.get("properties", {}),
        }
        if mp.get("from_variable"):
            normalized["from_variable"] = mp["from_variable"]
        if mp.get("to_variable"):
            normalized["to_variable"] = mp["to_variable"]
        result.append(normalized)

    return result


def normalize_response(raw_llm_data, db_path_or_discovery, db_type="sqlite"):
    """Normalize raw LLM output into a canonical query plan dict.

    Args:
        raw_llm_data: The raw dict from the LLM.
        db_path_or_discovery: Either a file path string (sqlite mode) or a
                              BackendDiscovery instance (any backend).
        db_type: One of "sqlite", "mongodb", "neo4j". Only used when
                 db_path_or_discovery is a string.

    Returns a normalized dict ready for query construction.
    """
    discovery = _resolve_discovery(db_path_or_discovery, db_type)
    tables = discovery.get_collections()

    action = raw_llm_data.get("action", "SELECT").upper()
    if action in ("GET", "FETCH", "RETRIEVE", "SHOW", "QUERY", "LIST"):
        action = "SELECT"
    elif action not in ("SELECT",):
        print(f"  [WARNING] Destructive action {action!r} overridden to SELECT")
        action = "SELECT"

    columns = extract_string_list(raw_llm_data.get("columns", []))
    clean_cols, aggs_from_cols = extract_aggregations_from_columns(columns)

    existing_aggs = normalize_aggregations(raw_llm_data.get("aggregations", []))
    all_aggs = existing_aggs + aggs_from_cols

    where_logic = str(raw_llm_data.get("where_logic", "AND")).upper()
    if where_logic not in ("AND", "OR"):
        where_logic = "AND"

    having_logic = str(raw_llm_data.get("having_logic", "AND")).upper()
    if having_logic not in ("AND", "OR"):
        having_logic = "AND"

    normalized = {
        "action": action,
        "db_type": db_type,
        "table": raw_llm_data.get("table", ""),
        "columns": clean_cols,
        "distinct": raw_llm_data.get("distinct", False),
        "joins": normalize_joins(
            raw_llm_data.get("joins", []),
            raw_llm_data.get("table", ""),
            discovery,
        ),
        "filters": normalize_filters(raw_llm_data.get("filters", [])),
        "group_by": extract_string_list(raw_llm_data.get("group_by", [])),
        "having": normalize_having(raw_llm_data.get("having", [])),
        "aggregations": all_aggs,
        "order_by": normalize_order_by(raw_llm_data.get("order_by", [])),
        "limit": raw_llm_data.get("limit"),
        "offset": raw_llm_data.get("offset"),
        "where_logic": where_logic,
        "having_logic": having_logic,
        "unwind": raw_llm_data.get("unwind"),
        "include_id": raw_llm_data.get("include_id", True),
        "match_patterns": _normalize_match_patterns(raw_llm_data.get("match_patterns", [])),
        "return_expressions": raw_llm_data.get("return_expressions", []),
    }

    normalized["joins"] = infer_missing_joins(normalized, tables, discovery)
    normalized = qualify_columns(normalized, tables)

    # Schema validation: reject queries that reference non-existent objects
    try:
        normalized = validate_against_schema(normalized, tables)
    except SchemaValidationError as e:
        print(f"  [ERROR] Schema validation failed: {e}")
        raise

    return normalized

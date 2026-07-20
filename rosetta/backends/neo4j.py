"""Neo4j Cypher query constructor (stub for future implementation).

Converts a normalized query plan into a Cypher query string.
Currently returns a descriptive error — full implementation deferred.
"""


def _strip_table_prefix(col):
    if "." in col:
        return col.split(".", 1)[1]
    return col


def build_cypher(data):
    """Build a Cypher query string from a normalized query plan.

    Currently a stub. Returns an error message with the plan that would be
    used once Neo4j graph traversal support is fully implemented.

    The Cypher constructor will need to:
      1. Map 'table' → node label for MATCH clause
      2. Map 'joins' → relationship patterns: (a)-[:REL_TYPE]->(b)
      3. Map 'match_patterns' → explicit MATCH clauses (when IR has them)
      4. Map 'filters' → WHERE clause
      5. Map 'group_by' + 'aggregations' → RETURN with aggregate functions
         (implicit grouping in Cypher)
      6. Map 'order_by' → ORDER BY
      7. Map 'limit' / 'offset' → LIMIT / SKIP
      8. Map 'distinct' → RETURN DISTINCT
      9. Wrap in OPTIONAL MATCH for LEFT JOIN semantics
     10. Use WITH for post-aggregation HAVING filtering
    """
    raise NotImplementedError(
        "Neo4j Cypher support is not yet implemented. "
        "The unified IR contains fields 'match_patterns' and "
        "'return_expressions' that will be used for graph query construction. "
        f"Plan received: table={data.get('table')}, "
        f"columns={data.get('columns')}, "
        f"filters={data.get('filters')}"
    )


def build_and_execute_cypher(data, connection_string, username="", password=""):
    """Build and execute a Cypher query against Neo4j.

    Currently a stub. Will use the neo4j Python driver when implemented.
    """
    raise NotImplementedError(
        "Neo4j support is not yet implemented. "
        "Install neo4j driver with: pip install neo4j"
    )

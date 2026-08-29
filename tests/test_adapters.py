"""Tests for SQLite and Neo4j query generation (no external services)."""

import pytest

from queryadapter.backends.sqlite import build_and_execute
from queryadapter.backends.neo4j import build_cypher


def test_sqlite_builds_parameterized_query(ecommerce_db):
    plan = {
        "action": "SELECT",
        "table": "customers",
        "columns": ["name", "city"],
        "filters": [{"column": "city", "operator": "=", "value": "New York"}],
        "order_by": [{"column": "name", "direction": "ASC"}],
    }
    query, params, rows = build_and_execute(plan, ecommerce_db)
    assert query.startswith("SELECT name, city FROM customers")
    assert "?" in query
    assert params == ["New York"]
    assert len(rows) == 2


def test_sqlite_join_and_aggregate(ecommerce_db):
    plan = {
        "action": "SELECT",
        "table": "customers",
        "columns": ["customers.name"],
        "joins": [
            {
                "type": "INNER",
                "table": "orders",
                "on": {"customers.id": "orders.customer_id"},
            }
        ],
        "aggregations": [
            {"function": "SUM", "column": "orders.total_amount", "alias": "total"}
        ],
        "group_by": ["customers.name"],
        "order_by": [{"column": "total", "direction": "DESC"}],
        "limit": 1,
    }
    query, params, rows = build_and_execute(plan, ecommerce_db)
    assert "JOIN" in query
    assert rows[0][1] == 1429.97


def test_sqlite_rejects_non_select(ecommerce_db):
    with pytest.raises(ValueError):
        build_and_execute(
            {"action": "DELETE", "table": "customers", "columns": []}, ecommerce_db
        )


def test_cypher_builds_from_match_patterns():
    plan = {
        "action": "SELECT",
        "db_type": "neo4j",
        "table": "Customer",
        "match_patterns": [
            {"variable": "c", "labels": ["Customer"]},
            {
                "variable": "o",
                "labels": ["Order"],
                "relationship_types": ["PLACED"],
                "direction": "OUTGOING",
                "from_variable": "c",
                "to_variable": "o",
            },
        ],
        "return_expressions": [
            {"expression": "c.name", "alias": "name"},
        ],
        "order_by": [{"column": "c.name", "direction": "ASC"}],
        "limit": 10,
    }
    query, params = build_cypher(plan)
    assert "MATCH (c:Customer)" in query
    assert "-[o:PLACED]->(o:Order)" in query
    assert "RETURN c.name AS name" in query
    assert "LIMIT 10" in query


def test_cypher_builds_relational_fallback():
    plan = {
        "action": "SELECT",
        "db_type": "neo4j",
        "table": "Customer",
        "columns": ["name"],
        "joins": [{"type": "INNER", "table": "Order"}],
    }
    query, params = build_cypher(plan)
    assert "MATCH (n:Customer)" in query
    assert "-[n1_rel:ORDER]->(n1:Order)" in query


def test_cypher_parameterizes_values():
    plan = {
        "action": "SELECT",
        "db_type": "neo4j",
        "table": "Customer",
        "columns": ["name"],
        "filters": [{"column": "name", "operator": "=", "value": "Alice"}],
    }
    query, params = build_cypher(plan)
    assert "WHERE name = $p0" in query
    assert params == {"p0": "Alice"}

"""Tests for schema/security validation."""

import pytest

from queryadapter.ir.validator import validate_against_schema, SchemaValidationError

TABLES = {
    "customers": {"id", "name", "city"},
    "orders": {"id", "customer_id", "total_amount"},
}


def test_accepts_valid_select():
    plan = {
        "action": "SELECT",
        "table": "customers",
        "columns": ["name", "city"],
        "filters": [{"column": "city", "operator": "=", "value": "NYC"}],
    }
    assert validate_against_schema(plan, TABLES) == plan


def test_rejects_non_select_action():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {"action": "DELETE", "table": "customers", "columns": []}, TABLES
        )


def test_rejects_unknown_table():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {"action": "SELECT", "table": "missing", "columns": []}, TABLES
        )


def test_rejects_unknown_column():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {"action": "SELECT", "table": "customers", "columns": ["nope"]},
            TABLES,
        )


def test_rejects_disallowed_operator():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {
                "action": "SELECT",
                "table": "customers",
                "columns": ["name"],
                "filters": [{"column": "name", "operator": "EXEC", "value": "x"}],
            },
            TABLES,
        )


def test_rejects_injection_in_identifier():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {"action": "SELECT", "table": "customers; DROP TABLE customers", "columns": []},
            TABLES,
        )


def test_sanitizes_invalid_logic():
    plan = {
        "action": "SELECT",
        "table": "customers",
        "columns": ["name"],
        "where_logic": "NOT A LOGIC",
    }
    validated = validate_against_schema(plan, TABLES)
    assert validated["where_logic"] == "AND"


def test_rejects_negative_limit():
    with pytest.raises(SchemaValidationError):
        validate_against_schema(
            {"action": "SELECT", "table": "customers", "columns": [], "limit": -1},
            TABLES,
        )


def test_validates_graph_plan_labels():
    graph_tables = {"Customer": {"name"}, ":PLACED": {"~from"}}
    plan = {
        "action": "SELECT",
        "db_type": "neo4j",
        "match_patterns": [
            {"variable": "c", "labels": ["Customer"]},
            {
                "variable": "r",
                "relationship_types": ["PLACED"],
                "from_variable": "c",
            },
        ],
    }
    assert validate_against_schema(plan, graph_tables) == plan


def test_graph_plan_rejects_unknown_label():
    graph_tables = {"Customer": {"name"}}
    plan = {
        "action": "SELECT",
        "db_type": "neo4j",
        "match_patterns": [{"variable": "x", "labels": ["Ghost"]}],
    }
    with pytest.raises(SchemaValidationError):
        validate_against_schema(plan, graph_tables)

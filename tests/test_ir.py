"""Tests for the IR structures and structural validation."""

import pytest

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


def test_query_plan_round_trip():
    plan = QueryPlan(
        action="SELECT",
        db_type="sqlite",
        table="orders",
        columns=["id", "total_amount"],
        filters=[Filter("total_amount", ">", 100)],
        joins=[Join("INNER", "customers", {"orders.customer_id": "customers.id"})],
        aggregations=[Aggregation("SUM", "total_amount", "total")],
        order_by=[OrderBy("total", "DESC")],
        limit=10,
    )
    restored = QueryPlan.from_dict(plan.to_dict())
    assert restored == plan


def test_validate_plan_structure_rejects_missing_fields():
    with pytest.raises(IRValidationError):
        validate_plan_structure({"action": "SELECT", "table": "t"})


def test_validate_plan_structure_rejects_non_select():
    with pytest.raises(IRValidationError):
        validate_plan_structure(
            {"action": "DELETE", "table": "t", "columns": []}
        )


def test_validate_plan_structure_rejects_unknown_db_type():
    with pytest.raises(IRValidationError):
        validate_plan_structure(
            {"action": "SELECT", "table": "t", "columns": [], "db_type": "oracle"}
        )


def test_match_pattern_to_dict_preserves_relationship():
    mp = MatchPattern(
        variable="r",
        labels=["Customer"],
        relationship_types=["PLACED"],
        direction="OUTGOING",
        from_variable="c",
        to_variable="o",
        min_hops=1,
        max_hops=3,
    )
    d = mp.to_dict()
    assert d["relationship_types"] == ["PLACED"]
    assert d["min_hops"] == 1
    assert d["max_hops"] == 3
    restored = MatchPattern.from_dict(d)
    assert restored == mp

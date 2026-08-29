"""End-to-end tests for QueryAdapter using a deterministic fake provider."""

import pytest

from queryadapter import QueryAdapter, SafetyError, ValidationError
from queryadapter.core import QueryAdapter as CoreAdapter


def test_ask_returns_result(ecommerce_db, monkeypatch, fake_provider):
    provider_instance = fake_provider(
        plan={
            "action": "SELECT",
            "table": "customers",
            "columns": ["name", "city"],
            "filters": [{"column": "city", "operator": "=", "value": "New York"}],
        }
    )
    monkeypatch.setattr(
        "queryadapter.core.create_provider", lambda *a, **k: provider_instance
    )
    adapter = QueryAdapter(ecommerce_db)
    result = adapter.ask("show customers from New York")

    assert result.row_count == 2
    assert result.database == "sqlite"
    assert result.query.startswith("SELECT name, city FROM customers")
    assert provider_instance.json_calls == 1
    assert result.metadata["provider"] == "fake"


def test_schema_returns_discovered_tables(ecommerce_db, monkeypatch, fake_provider):
    monkeypatch.setattr(
        "queryadapter.core.create_provider", lambda *a, **k: fake_provider()
    )
    adapter = QueryAdapter(ecommerce_db)
    schema = adapter.schema()
    assert "customers" in schema["collections"]
    assert "orders" in schema["collections"]
    assert schema["ddl"].startswith("CREATE TABLE")


def test_read_only_blocks_write_actions(ecommerce_db, monkeypatch, fake_provider):
    provider_instance = fake_provider(
        plan={"action": "DELETE", "table": "customers", "columns": []}
    )
    monkeypatch.setattr(
        "queryadapter.core.create_provider", lambda *a, **k: provider_instance
    )
    adapter = QueryAdapter(ecommerce_db, read_only=True)
    with pytest.raises(SafetyError):
        adapter.ask("delete all customers")


def test_default_limit_is_applied(ecommerce_db, monkeypatch, fake_provider):
    provider_instance = fake_provider(
        plan={"action": "SELECT", "table": "customers", "columns": ["name"]}
    )
    monkeypatch.setattr(
        "queryadapter.core.create_provider", lambda *a, **k: provider_instance
    )
    adapter = QueryAdapter(ecommerce_db, default_limit=1)
    result = adapter.ask("show all customers")
    assert result.row_count == 1
    assert "LIMIT ?" in result.query


def test_invalid_action_without_read_only_is_validation_error(
    ecommerce_db, monkeypatch, fake_provider
):
    provider_instance = fake_provider(
        plan={"action": "UPDATE", "table": "customers", "columns": []}
    )
    monkeypatch.setattr(
        "queryadapter.core.create_provider", lambda *a, **k: provider_instance
    )
    adapter = QueryAdapter(ecommerce_db, read_only=False)
    with pytest.raises(ValidationError):
        adapter.ask("update customers")


def test_repr(ecommerce_db):
    adapter = QueryAdapter(ecommerce_db)
    assert "QueryAdapter" in repr(adapter)
    assert "sqlite" in repr(adapter)

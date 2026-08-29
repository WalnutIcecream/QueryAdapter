"""Shared fixtures for the QueryAdapter test suite."""

import sqlite3

import pytest


@pytest.fixture
def ecommerce_db(tmp_path):
    """Create a deterministic SQLite e-commerce database."""
    db_path = str(tmp_path / "ecommerce.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT,
            joined_date TEXT
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price REAL
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            status TEXT,
            total_amount REAL
        );

        INSERT INTO customers VALUES
            (1, 'Alice', 'New York', '2024-01-15'),
            (2, 'Bob', 'Los Angeles', '2024-02-20'),
            (3, 'Carol', 'Chicago', '2024-03-10'),
            (4, 'Dave', 'New York', '2024-04-05');

        INSERT INTO products VALUES
            (1, 'Laptop', 'Electronics', 1299.99),
            (2, 'Mouse', 'Electronics', 29.99),
            (3, 'Desk', 'Furniture', 249.99);

        INSERT INTO orders VALUES
            (1, 1, 'delivered', 1379.98),
            (2, 1, 'delivered', 49.99),
            (3, 2, 'shipped', 149.99),
            (4, 3, 'processing', 899.98),
            (5, 4, 'delivered', 29.99);
        """
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def fake_provider():
    """A deterministic provider that returns a canned plan."""
    from queryadapter.providers.base import Provider

    class FakeProvider(Provider):
        name = "fake"

        def __init__(self, plan=None, text="ok"):
            self.plan = plan or {
                "action": "SELECT",
                "table": "customers",
                "columns": ["name", "city"],
                "filters": [],
            }
            self.text = text
            self.json_calls = 0
            self.text_calls = 0

        def generate_json(self, prompt, *, system=None, json_schema=None):
            self.json_calls += 1
            return dict(self.plan)

        def generate_text(self, prompt, *, system=None):
            self.text_calls += 1
            return self.text

    return FakeProvider

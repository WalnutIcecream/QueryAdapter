#!/usr/bin/env python3
"""
QueryAdapter demo — demonstrates all three database backends without external servers.

Usage:
    python demos/run_demo.py
"""
import json
import os
import sqlite3
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

GREEN = "\033[32m"
CYAN  = "\033[36m"
BOLD  = "\033[1m"
RESET = "\033[0m"

def header(text):
    print(f"\n{BOLD}{'='*64}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'='*64}{RESET}")

def section(text):
    print(f"\n{CYAN}{'—'*56}{RESET}")
    print(f"{CYAN}  {text}{RESET}")
    print(f"{CYAN}{'—'*56}{RESET}")

def ok(label):
    print(f"  {GREEN}✓{RESET} {label}")

def info(key, val):
    print(f"  {BOLD}{key}:{RESET} {val}")


def create_sqlite_db():
    """Create a temporary SQLite e-commerce database for the demo."""
    db_path = tempfile.mktemp(suffix=".db", prefix="queryadapter_demo_")
    cx = sqlite3.connect(db_path)
    cx.executescript("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            city TEXT,
            joined_date TEXT
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            stock INTEGER
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT,
            status TEXT,
            total_amount REAL
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL
        );
        INSERT INTO customers VALUES
            (1, 'Alice Johnson', 'alice@e.com', 'New York', '2024-01-15'),
            (2, 'Bob Smith', 'bob@e.com', 'Los Angeles', '2024-02-20'),
            (3, 'Carol White', 'carol@e.com', 'Chicago', '2024-03-10'),
            (4, 'Dave Brown', 'dave@e.com', 'New York', '2024-04-05'),
            (5, 'Eve Davis', 'eve@e.com', 'Los Angeles', '2024-05-12');
        INSERT INTO products VALUES
            (1, 'Laptop Pro', 'Electronics', 1299.99, 50),
            (2, 'Wireless Mouse', 'Electronics', 29.99, 200),
            (3, 'Mechanical Keyboard', 'Electronics', 149.99, 75),
            (4, 'USB-C Hub', 'Accessories', 49.99, 150),
            (5, 'Monitor 27"', 'Electronics', 349.99, 30),
            (6, 'Desk Chair', 'Furniture', 249.99, 20),
            (7, 'Standing Desk', 'Furniture', 599.99, 10),
            (8, 'Webcam HD', 'Electronics', 89.99, 100);
        INSERT INTO orders VALUES
            (1, 1, '2024-06-01', 'delivered', 1379.98),
            (2, 1, '2024-06-15', 'delivered', 49.99),
            (3, 2, '2024-07-01', 'shipped', 149.99),
            (4, 3, '2024-07-10', 'processing', 899.98),
            (5, 4, '2024-08-01', 'delivered', 29.99),
            (6, 5, '2024-08-05', 'shipped', 599.98);
        INSERT INTO order_items VALUES
            (1, 1, 1, 1, 1299.99), (2, 1, 2, 1, 29.99),
            (3, 1, 4, 1, 49.99),  (4, 2, 4, 1, 49.99),
            (5, 3, 3, 1, 149.99), (6, 4, 5, 1, 349.99),
            (7, 4, 7, 1, 599.99), (8, 6, 6, 1, 249.99),
            (9, 6, 5, 1, 349.99);
    """)
    cx.commit()
    cx.close()
    return db_path


# ─────────────────────────────────────────────────────────────
def demo_sqlite():
    header("SQLITE — Full Text-to-SQL Pipeline")
    from queryadapter.nlp.normalizer import normalize_response
    from queryadapter.backends.discovery import get_discovery
    from queryadapter.backends.sqlite import build_and_execute

    db_path = create_sqlite_db()
    section("Schema Discovery")
    disc = get_discovery("sqlite", db_path)
    schema = disc.get_collections()
    ok(f"Discovered {len(schema)} tables")
    for table, cols in sorted(schema.items()):
        info(table, ", ".join(sorted(cols)))
    info("auto FK inference", str(disc.infer_relationships("orders", "customers")))

    section("Query 1 — Filter + Join + Order")
    plan = {
        "action": "SELECT", "table": "customers",
        "columns": ["name", "city"],
        "joins": [{"type": "INNER", "table": "orders",
                   "on": {"customers.id": "orders.customer_id"}}],
        "filters": [{"column": "city", "operator": "=", "value": "New York"}],
        "order_by": [{"column": "name", "direction": "ASC"}],
    }
    norm = normalize_response(plan, db_path)
    query, params, rows = build_and_execute(norm, db_path)
    ok("plan normalized + validated")
    info("SQL", query)
    info("params", str(params))
    info("rows", str(len(rows)))
    for r in rows:
        print(f"      {r}")

    section("Query 2 — Aggregate + Group By")
    plan2 = {
        "action": "SELECT", "table": "customers", "columns": ["city"],
        "joins": [{"type": "INNER", "table": "orders",
                   "on": {"customers.id": "orders.customer_id"}}],
        "group_by": ["city"],
        "aggregations": [{"function": "AVG", "column": "total_amount",
                          "alias": "avg_total"}],
        "order_by": [{"column": "avg_total", "direction": "DESC"}],
    }
    norm2 = normalize_response(plan2, db_path)
    query, params, rows = build_and_execute(norm2, db_path)
    info("SQL", query)
    for r in rows:
        print(f"      {r[0]}: ${r[1]:.2f}")

    os.unlink(db_path)


# ─────────────────────────────────────────────────────────────
def demo_mongodb():
    header("MONGODB — MQL Aggregation Pipeline Construction")
    from queryadapter.backends.mongodb import build_mql_pipeline

    section("Pipeline: filter + project + sort + limit")
    plan = {
        "action": "SELECT", "db_type": "mongodb", "table": "products",
        "columns": ["name", "price", "category"],
        "filters": [
            {"column": "category", "operator": "=", "value": "Electronics"},
            {"column": "price", "operator": "<", "value": 200},
        ],
        "order_by": [{"column": "price", "direction": "ASC"}],
        "limit": 5, "include_id": False,
    }
    pipeline = build_mql_pipeline(plan)
    ok(f"Generated {len(pipeline)} pipeline stages")
    for i, stage in enumerate(pipeline):
        info(f"stage {i}", json.dumps(stage, default=str))

    section("Pipeline: group by + sum + count")
    plan2 = {
        "action": "SELECT", "db_type": "mongodb", "table": "products",
        "group_by": ["category"],
        "aggregations": [
            {"function": "SUM", "column": "price", "alias": "total_value"},
            {"function": "COUNT", "column": "*", "alias": "product_count"},
        ],
        "order_by": [{"column": "total_value", "direction": "DESC"}],
        "include_id": False,
    }
    pipeline2 = build_mql_pipeline(plan2)
    for i, stage in enumerate(pipeline2):
        info(f"stage {i}", json.dumps(stage, default=str))

    section("Pipeline: OR logic ($or)")
    plan3 = {
        "action": "SELECT", "db_type": "mongodb", "table": "products",
        "columns": ["name", "category"],
        "filters": [
            {"column": "category", "operator": "=", "value": "Electronics"},
            {"column": "category", "operator": "=", "value": "Furniture"},
        ],
        "where_logic": "OR", "include_id": False,
    }
    stages = build_mql_pipeline(plan3)
    match = [s for s in stages if "$match" in s][0]
    ok("$or operator")
    info("$match", json.dumps(match, default=str))


# ─────────────────────────────────────────────────────────────
def demo_neo4j():
    header("NEO4J — Graph Schema + Query Stub")
    from queryadapter.ir.query_plan import QueryPlan, MatchPattern, OrderBy

    section("Graph Schema (discovered when connected)")
    ok("labels: Customer, Order, Product, Category, Warehouse")
    ok("relationship types: PLACED, CONTAINS, BELONGS_TO, STORED_AT")
    ok("property keys: id, name, email, city, price, stock, total, status")

    section("IR: 'customers who bought Electronics' (4-hop traversal)")
    plan = QueryPlan(
        action="SELECT", db_type="neo4j", table="Customer",
        columns=["name", "email"],
        match_patterns=[
            MatchPattern(variable="c", labels=["Customer"]),
            MatchPattern(variable="o", labels=["Order"],
                         relationship_types=["PLACED"], direction="OUTGOING",
                         from_variable="c", to_variable="o"),
            MatchPattern(variable="p", labels=["Product"],
                         relationship_types=["CONTAINS"], direction="OUTGOING",
                         from_variable="o", to_variable="p"),
            MatchPattern(variable="cat", labels=["Category"],
                         relationship_types=["BELONGS_TO"], direction="OUTGOING",
                         from_variable="p", to_variable="cat",
                         properties={"name": "Electronics"}),
        ],
        return_expressions=[
            {"expression": "c.name", "alias": "customer"},
            {"expression": "c.email", "alias": "email"},
        ],
        order_by=[OrderBy(column="c.name", direction="ASC")],
    )
    ok("unified IR with match_patterns and return_expressions")
    info("plan", json.dumps(plan.to_dict(), indent=2, default=str)[:200] + "...")

    section("Generated Cypher (when backend implemented)")
    cypher = """MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
MATCH (p)-[:BELONGS_TO]->(cat:Category {name: 'Electronics'})
RETURN c.name AS customer, c.email AS email
ORDER BY c.name ASC"""
    print(f"    {cypher}")


# ─────────────────────────────────────────────────────────────
def demo_conversation():
    header("CONVERSATION — Multi-Turn Context + Intent Routing")
    from queryadapter.conversation.context import ConversationContext, classify_intent

    ctx = ConversationContext("demo", "sqlite", "db")
    section("Intent Classification")
    tests = [
        ("show all customers from New York", "query"),
        ("explain the orders table", "chat"),
        ("count how many products are in stock", "query"),
        ("help me write a query", "chat"),
        ("find products under $50", "query"),
        ("describe the schema", "chat"),
    ]
    for text, expected in tests:
        intent = classify_intent(text, ctx)
        mark = "✓" if intent == expected else "✗"
        print(f"  {mark} [{intent:5s}] {text}")

    section("Follow-Up Resolution (pronoun → prior context)")
    ctx.add_turn("user", "show customers from New York", intent="query")
    ctx.add_turn("assistant", "2 rows returned", intent="query",
                 json_plan={"table": "customers",
                            "filters": [{"column": "city", "operator": "=",
                                         "value": "New York"}]},
                 results=[("Alice", "NY"), ("Dave", "NY")])
    q = "how many of them have placed orders?"
    resolved = ctx.resolve_follow_up(q)
    ok(f"'{q}'")
    print(f"      → {resolved}")


# ─────────────────────────────────────────────────────────────
def demo_architecture():
    header("ARCHITECTURE — Two-Tier Model + Multi-Backend")
    print("""
  User Input
      │
  [Intent Router] ───── query ──→ T5-small (60M, ~20ms)
      │                             │
      └───────── chat ──→ Ollama llama3.2:3b (~1000ms)
                                     │
                              [Normalizer]
                              [Schema Validator]
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                 SQLite          MongoDB MQL      Neo4j Cypher
""")


# ─────────────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}QueryAdapter v0.1.0 — Natural Language → SQL · MQL · Cypher{RESET}")
    print(f"  A multi-backend natural-language query pipeline.\n")

    demo_architecture()
    demo_sqlite()
    demo_mongodb()
    demo_neo4j()
    demo_conversation()

    header("QUICK START")
    print("""
  pip install -e /path/to/QueryAdapter
  queryadapter ask path/to/any.db "show all users"

  from queryadapter import QueryAdapter
  adapter = QueryAdapter("app.db")
  result = adapter.ask("show all users")
  print(result.data)
""")


if __name__ == "__main__":
    main()

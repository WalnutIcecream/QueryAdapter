#!/usr/bin/env python3
"""Neo4j demo graph seeder.

Usage:
    python demos/neo4j/setup_db.py [bolt_uri] [username] [password]

Seeds an e-commerce graph: Customer-[PLACED]->Order-[CONTAINS]->Product,
Product-[BELONGS_TO]->Category, Product-[STORED_AT]->Warehouse.
"""

import sys

CYPHER = """
CREATE (:Category {name: 'Electronics'});
CREATE (:Category {name: 'Furniture'});
CREATE (:Customer {id: 1, name: 'Alice', city: 'New York'});
CREATE (:Customer {id: 2, name: 'Bob', city: 'Los Angeles'});
CREATE (:Product {id: 1, name: 'Laptop Pro', price: 1299.99});
CREATE (:Product {id: 2, name: 'Desk Chair', price: 249.99});
CREATE (:Warehouse {name: 'A', location: 'East'});

MATCH (p:Product {id: 1}), (c:Category {name: 'Electronics'})
  CREATE (p)-[:BELONGS_TO]->(c);
MATCH (p:Product {id: 2}), (c:Category {name: 'Furniture'})
  CREATE (p)-[:BELONGS_TO]->(c);
MATCH (p:Product {id: 1}), (w:Warehouse {name: 'A'})
  CREATE (p)-[:STORED_AT {quantity: 30}]->(w);

MATCH (c:Customer {id: 1}), (p:Product {id: 1})
  CREATE (c)-[:PLACED {date: '2024-06-01'}]->(o:Order {id: 1, total: 1299.99})
  CREATE (o)-[:CONTAINS {quantity: 1}]->(p);
MATCH (c:Customer {id: 2}), (p:Product {id: 2})
  CREATE (c)-[:PLACED {date: '2024-07-01'}]->(o2:Order {id: 2, total: 249.99})
  CREATE (o2)-[:CONTAINS {quantity: 1}]->(p);
""".strip()


def seed(uri, user, password):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("Error: neo4j driver not installed.  pip install neo4j")
        return False
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as e:
        print(f"Cannot connect to {uri}: {e}")
        return False
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for stmt in CYPHER.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("//"):
                s.run(stmt)
    driver.close()
    print("Seeded: 3 Categories, 2 Customers, 2 Products, 1 Warehouse, 2 Orders")
    print("Relationships: BELONGS_TO, STORED_AT, PLACED, CONTAINS")
    return True


if __name__ == "__main__":
    uri      = sys.argv[1] if len(sys.argv) > 1 else "bolt://localhost:7687"
    user     = sys.argv[2] if len(sys.argv) > 2 else "neo4j"
    password = sys.argv[3] if len(sys.argv) > 3 else "password"
    if not seed(uri, user, password):
        print("\nStart Neo4j first, then re-run:")
        print(f"  neo4j start")
        print(f"  python {__file__} {uri} {user} {password}")

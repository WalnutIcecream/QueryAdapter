#!/usr/bin/env python3
"""MongoDB demo data seeder.

Usage:
    python demos/mongo/setup_db.py [mongodb_uri]

If a MongoDB server is available, seeds it with an e-commerce dataset.
If not, displays the document structure and advises how to start mongod.
"""

import json
import os
import sys

DEMO_DATA = {
    "customers": [
        {"_id": 1, "name": "Alice Johnson", "email": "alice@e.com",
         "address": {"city": "New York", "state": "NY"}, "joined": "2024-01-15"},
        {"_id": 2, "name": "Bob Smith", "email": "bob@e.com",
         "address": {"city": "Los Angeles", "state": "CA"}, "joined": "2024-02-20"},
        {"_id": 3, "name": "Carol White", "email": "carol@e.com",
         "address": {"city": "Chicago", "state": "IL"}, "joined": "2024-03-10"},
    ],
    "products": [
        {"_id": 1, "name": "Laptop Pro", "category": "Electronics", "price": 1299.99, "stock": 50},
        {"_id": 2, "name": "Wireless Mouse", "category": "Electronics", "price": 29.99, "stock": 200},
        {"_id": 3, "name": "Desk Chair", "category": "Furniture", "price": 249.99, "stock": 20},
    ],
    "orders": [
        {"_id": 1, "customer_id": 1, "date": "2024-06-01", "status": "delivered",
         "total": 1379.98, "items": [{"product_id": 1, "quantity": 1, "price": 1299.99}]},
        {"_id": 2, "customer_id": 2, "date": "2024-07-01", "status": "shipped",
         "total": 149.99, "items": [{"product_id": 2, "quantity": 1, "price": 149.99}]},
    ],
}


def seed(uri):
    try:
        from pymongo import MongoClient
    except ImportError:
        print("Error: pymongo not installed.  pip install pymongo")
        return False
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
    except Exception as e:
        print(f"Cannot connect to {uri}: {e}")
        return False
    db = client[uri.rsplit("/", 1)[-1]]
    for coll, docs in DEMO_DATA.items():
        db[coll].delete_many({})
        if docs:
            db[coll].insert_many(docs)
        print(f"  Seeded {coll}: {len(docs)} documents")
    client.close()
    return True


if __name__ == "__main__":
    uri = sys.argv[1] if len(sys.argv) > 1 else "mongodb://localhost:27017/ecommerce"
    if not seed(uri):
        print("\nStart MongoDB first, then re-run:")
        print(f"  mongod --dbpath /tmp/mongo")
        print(f"  python {__file__} {uri}")

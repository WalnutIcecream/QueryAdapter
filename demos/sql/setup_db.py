#!/usr/bin/env python3
"""Seed a SQLite database for use with rosetta.

Usage:
    python demos/sql/setup_db.py [output_path]

Creates an e-commerce database with customers, products, orders, and
order_items tables plus sample data.
"""
import sqlite3
import os
import sys

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "ecommerce.db")

SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT,
    city TEXT, joined_date TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT,
    price REAL, stock INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT,
    status TEXT, total_amount REAL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER,
    quantity INTEGER, unit_price REAL
);
INSERT OR IGNORE INTO customers VALUES
    (1,'Alice Johnson','alice@e.com','New York','2024-01-15'),
    (2,'Bob Smith','bob@e.com','Los Angeles','2024-02-20'),
    (3,'Carol White','carol@e.com','Chicago','2024-03-10'),
    (4,'Dave Brown','dave@e.com','New York','2024-04-05'),
    (5,'Eve Davis','eve@e.com','Los Angeles','2024-05-12');
INSERT OR IGNORE INTO products VALUES
    (1,'Laptop Pro','Electronics',1299.99,50),
    (2,'Wireless Mouse','Electronics',29.99,200),
    (3,'Mechanical Keyboard','Electronics',149.99,75),
    (4,'USB-C Hub','Accessories',49.99,150),
    (5,'Monitor 27"','Electronics',349.99,30),
    (6,'Desk Chair','Furniture',249.99,20),
    (7,'Standing Desk','Furniture',599.99,10),
    (8,'Webcam HD','Electronics',89.99,100);
INSERT OR IGNORE INTO orders VALUES
    (1,1,'2024-06-01','delivered',1379.98),
    (2,1,'2024-06-15','delivered',49.99),
    (3,2,'2024-07-01','shipped',149.99),
    (4,3,'2024-07-10','processing',899.98),
    (5,4,'2024-08-01','delivered',29.99),
    (6,5,'2024-08-05','shipped',599.98);
INSERT OR IGNORE INTO order_items VALUES
    (1,1,1,1,1299.99),(2,1,2,1,29.99),(3,1,4,1,49.99),
    (4,2,4,1,49.99),(5,3,3,1,149.99),(6,4,5,1,349.99),
    (7,4,7,1,599.99),(8,6,6,1,249.99),(9,6,5,1,349.99);
"""

path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH

if os.path.exists(path):
    print(f"Database already exists: {path}")
    print(f"Delete it first or use a different path.")
    sys.exit(1)

cx = sqlite3.connect(path)
cx.executescript(SQL)
cx.commit()
cx.close()

print(f"Created {path}")
print(f"  customers: 5 rows")
print(f"  products:  8 rows")
print(f"  orders:    6 rows")
print(f"  order_items: 9 rows")
print()
print(f"Try: rosetta {path} --interactive")

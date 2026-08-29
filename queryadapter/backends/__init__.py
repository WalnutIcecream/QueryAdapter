"""
queryadapter.backends — Database-specific query constructors and schema discovery.

Supported backends:
  - SQLite:   Full implementation
  - MongoDB:  MQL aggregation pipeline builder
  - Neo4j:    Cypher query generation and execution
"""

from queryadapter.backends.discovery import (
    get_discovery,
    BackendDiscovery,
    SQLiteDiscovery,
    MongoDBDiscovery,
    Neo4jDiscovery,
)
from queryadapter.backends.sqlite import build_and_execute
from queryadapter.backends.mongodb import build_mql_pipeline, build_and_execute_mql
from queryadapter.backends.neo4j import build_cypher, build_and_execute_cypher

__all__ = [
    "get_discovery",
    "BackendDiscovery",
    "SQLiteDiscovery",
    "MongoDBDiscovery",
    "Neo4jDiscovery",
    "build_and_execute",
    "build_mql_pipeline",
    "build_and_execute_mql",
    "build_cypher",
    "build_and_execute_cypher",
]

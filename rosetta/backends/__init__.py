"""
rosetta.backends — Database-specific query constructors and schema discovery.

Supported backends:
  - SQLite:   Full implementation
  - MongoDB:  MQL aggregation pipeline builder
  - Neo4j:    Cypher stub (node labels, relationships, patterns defined)
"""

from rosetta.backends.discovery import (
    get_discovery,
    BackendDiscovery,
    SQLiteDiscovery,
    MongoDBDiscovery,
    Neo4jDiscovery,
)
from rosetta.backends.sqlite import build_and_execute
from rosetta.backends.mongodb import build_mql_pipeline, build_and_execute_mql
from rosetta.backends.neo4j import build_and_execute_cypher

__all__ = [
    "get_discovery",
    "BackendDiscovery",
    "SQLiteDiscovery",
    "MongoDBDiscovery",
    "Neo4jDiscovery",
    "build_and_execute",
    "build_mql_pipeline",
    "build_and_execute_mql",
    "build_and_execute_cypher",
]

"""Backend-specific schema discovery adapters.

Each adapter provides a uniform interface for:
- Listing collections/tables and their fields
- Getting DDL (Data Definition Language) text for the NLP model
- Inferring relationships/foreign keys for auto-join detection
"""

import json
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional


class BackendDiscovery(ABC):
    """Abstract interface for schema discovery across database types."""

    @abstractmethod
    def get_collections(self) -> dict[str, set[str]]:
        """Return {collection_name: {field_name, ...}}."""
        ...

    @abstractmethod
    def get_ddl(self) -> str:
        """Return a text representation of the schema for the NLP model."""
        ...

    @abstractmethod
    def infer_relationships(self, main: str, target: str) -> dict:
        """Return a join condition dict {left_col: right_col} or {}."""
        ...


class SQLiteDiscovery(BackendDiscovery):
    """Schema discovery for SQLite databases."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_collections(self) -> dict[str, set[str]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        table_names = [r[0] for r in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        tables = {}
        for name in table_names:
            tables[name] = {row[1] for row in cursor.execute(
                f"PRAGMA table_info({name})"
            )}
        conn.close()
        return tables

    def get_ddl(self) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        conn.close()
        ddl_statements = [r[0] for r in rows]
        return "\n\n".join(ddl_statements) if ddl_statements else "-- No tables found"

    def infer_relationships(self, main: str, target: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        main_cols = {row[1] for row in cursor.execute(
            f"PRAGMA table_info({main})"
        )}
        target_cols = {row[1] for row in cursor.execute(
            f"PRAGMA table_info({target})"
        )}
        conn.close()

        singular = target.rstrip("s")
        fk_candidates = [c for c in main_cols if c == f"{singular}_id" or c == f"{target}_id"]
        if fk_candidates:
            return {f"{main}.{fk_candidates[0]}": f"{target}.id"}

        main_singular = main.rstrip("s")
        rev_candidates = [c for c in target_cols if c == f"{main_singular}_id"]
        if rev_candidates:
            return {f"{main}.id": f"{target}.{rev_candidates[0]}"}

        return {}

    def get_table_columns(self, table: str) -> set[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cols = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        conn.close()
        return cols


class MongoDBDiscovery(BackendDiscovery):
    """Schema discovery for MongoDB collections.

    Since MongoDB is schemaless, we sample documents to infer field names.
    Connection string format: mongodb://host:port/database
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._client = None
        self._db = None

    @property
    def client(self):
        if self._client is None:
            try:
                from pymongo import MongoClient
            except ImportError:
                raise ImportError(
                    "pymongo is required for MongoDB support. "
                    "Install it with: pip install pymongo"
                )
            self._client = MongoClient(self.connection_string)
            db_name = self.connection_string.rsplit("/", 1)[-1]
            self._db = self._client[db_name]
        return self._client

    @property
    def database(self):
        if self._db is None:
            _ = self.client
        return self._db

    def get_collections(self) -> dict[str, set[str]]:
        try:
            collections = {}
            sample_size = 10
            for name in self.database.list_collection_names():
                if name.startswith("system."):
                    continue
                fields = set()
                for doc in self.database[name].find().limit(sample_size):
                    fields.update(self._extract_fields(doc))
                collections[name] = fields
            return collections
        except Exception:
            return {}

    def get_ddl(self) -> str:
        collections = self.get_collections()
        if not collections:
            return "// No collections found in MongoDB database"
        lines = []
        for name, fields in sorted(collections.items()):
            field_list = ", ".join(sorted(fields)) if fields else "_id"
            lines.append(f"Collection: {name}\n  Fields: {field_list}")
        return "\n\n".join(lines)

    def infer_relationships(self, main: str, target: str) -> dict:
        main_cols = self.get_collections().get(main, set())
        singular = target.rstrip("s")
        fk = f"{singular}_id"
        if fk in main_cols:
            return {f"{main}.{fk}": f"{target}._id"}
        return {}

    def close(self):
        if self._client:
            self._client.close()

    @staticmethod
    def _extract_fields(doc: dict, prefix: str = "") -> set[str]:
        fields = set()
        for key, value in doc.items():
            full_key = f"{prefix}.{key}" if prefix else key
            fields.add(full_key)
            if isinstance(value, dict):
                fields.update(MongoDBDiscovery._extract_fields(value, full_key))
        return fields


class Neo4jDiscovery(BackendDiscovery):
    """Schema discovery for Neo4j graph databases.

    Connection string format: bolt://host:port or neo4j://host:port
    """

    def __init__(self, connection_string: str, username: str = "", password: str = ""):
        self.connection_string = connection_string
        self.username = username
        self.password = password
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError:
                raise ImportError(
                    "neo4j is required for Neo4j support. "
                    "Install it with: pip install neo4j"
                )
            auth = None
            if self.username and self.password:
                auth = (self.username, self.password)
            self._driver = GraphDatabase.driver(self.connection_string, auth=auth)
        return self._driver

    def get_collections(self) -> dict[str, set[str]]:
        try:
            with self.driver.session() as session:
                result = session.run("""
                    CALL db.labels() YIELD label
                    RETURN collect(label) AS labels
                """)
                labels = result.single()["labels"]

                result = session.run("""
                    CALL db.relationshipTypes() YIELD relationshipType
                    RETURN collect(relationshipType) AS types
                """)
                rel_types = result.single()["types"]

                collections = {}
                for label in labels:
                    result = session.run(
                        f"MATCH (n:{label}) RETURN n LIMIT 5"
                    )
                    fields = set()
                    for record in result:
                        node = record["n"]
                        fields.update(node.keys())
                    collections[label] = fields
                    collections[label].add("~id")

                for rel_type in rel_types:
                    collections[f":{rel_type}"] = {"~from", "~to", "~type"}

                return collections
        except Exception:
            return {}

    def get_ddl(self) -> str:
        try:
            with self.driver.session() as session:
                result = session.run("CALL db.schema.visualization()")
                record = result.single()
                if record and record.get("nodes"):
                    lines = ["// Neo4j Graph Schema"]
                    for node in record["nodes"]:
                        labels = ":".join(node.get("labels", []))
                        props = node.get("properties", {})
                        lines.append(f"Node ({labels}) {{ {json.dumps(props)} }}")
                    for rel in record.get("relationships", []):
                        rtype = rel.get("type", "REL")
                        lines.append(f"Relationship -[:{rtype}]-")
                    return "\n".join(lines)
        except Exception:
            pass
        return "// Neo4j schema — run CALL db.schema.visualization()"

    def infer_relationships(self, main: str, target: str) -> dict:
        return {}

    def close(self):
        if self._driver:
            self._driver.close()


def get_discovery(db_type: str, connection_string: str, **kwargs) -> BackendDiscovery:
    """Factory: return the appropriate BackendDiscovery for the given db_type."""
    if db_type == "sqlite":
        return SQLiteDiscovery(connection_string)
    elif db_type == "mongodb":
        return MongoDBDiscovery(connection_string)
    elif db_type == "neo4j":
        username = kwargs.get("username", "")
        password = kwargs.get("password", "")
        return Neo4jDiscovery(connection_string, username, password)
    else:
        raise ValueError(f"Unknown db_type: {db_type!r}. Supported: sqlite, mongodb, neo4j")

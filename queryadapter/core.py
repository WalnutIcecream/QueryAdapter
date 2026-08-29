"""Public QueryAdapter facade.

This is the single integration point. Internals are organized as independent
layers (ir, nlp, backends, providers, conversation) and QueryAdapter wires
them together with a minimal, opinionated API, enforcing read-only safety and
provider independence at the boundary.
"""

import json
import time
from typing import Any, Optional

from queryadapter.config import QueryAdapterConfig
from queryadapter.errors import (
    ConfigurationError,
    ConnectionError,
    IntentResolutionError,
    SafetyError,
    SchemaError,
    ValidationError,
)
from queryadapter.providers import create_provider
from queryadapter.result import Result
from queryadapter.cache import SchemaCache

from queryadapter.backends.discovery import get_discovery
from queryadapter.backends.sqlite import build_and_execute as build_sql
from queryadapter.backends.mongodb import build_and_execute_mql
from queryadapter.backends.neo4j import build_and_execute_cypher
from queryadapter.nlp.normalizer import normalize_response

SUPPORTED_DB_TYPES = {"sqlite", "mongodb", "neo4j"}

_DB_LABELS = {"sqlite": "SQL", "mongodb": "MQL", "neo4j": "Cypher"}


class QueryAdapter:
    """Natural-language querying over SQL, NoSQL, and graph databases.

    Minimal usage::

        from queryadapter import QueryAdapter

        adapter = QueryAdapter("postgresql://...")
        result = adapter.ask("Show my top customers")

    Args:
        database: Connection string or path. For SQLite pass a file path; for
            MongoDB pass ``mongodb://...``; for Neo4j pass ``bolt://...``.
        db_type: ``"sqlite"``, ``"mongodb"``, or ``"neo4j"``. Auto-detected
            from the ``database`` prefix when omitted.
        provider: ``"ollama"`` (default), ``"openai"``, or ``"anthropic"``.
        model: Optional model name override for the provider.
        api_key: Optional API key override (else read from environment).
        base_url: Optional endpoint override (OpenAI-compatible/Ollama host).
        read_only: When ``True`` (default) all writes are blocked.
        metadata: Optional semantic hints keyed by ``"table.column"``.
        cache_ttl: Seconds to cache discovered schema metadata.
        default_limit: Cap applied when a query has no explicit limit.
        max_limit: Hard ceiling applied to every query's limit.
        username: Neo4j username.
        password: Neo4j password.
    """

    def __init__(
        self,
        database: str,
        db_type: Optional[str] = None,
        *,
        provider: str = "ollama",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        read_only: bool = True,
        metadata: Optional[dict[str, str]] = None,
        cache_ttl: int = 300,
        default_limit: Optional[int] = None,
        max_limit: int = 1000,
        username: str = "",
        password: str = "",
        **kwargs,
    ):
        if not database:
            raise ConfigurationError("A database connection string is required")

        resolved_type = db_type or self._detect_db_type(database)
        if resolved_type not in SUPPORTED_DB_TYPES:
            raise ConfigurationError(
                f"Unsupported db_type {resolved_type!r}. "
                f"Supported: {sorted(SUPPORTED_DB_TYPES)}"
            )

        self.database = database
        self.db_type = resolved_type
        self.read_only = read_only
        self.metadata = metadata or {}
        self.default_limit = default_limit
        self.max_limit = max_limit

        self.config = QueryAdapterConfig(
            db_type=resolved_type,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            read_only=read_only,
            metadata=self.metadata,
            cache_ttl=cache_ttl,
            default_limit=default_limit,
            max_limit=max_limit,
            extra=kwargs,
        )

        self._provider = create_provider(
            provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            **kwargs,
        )
        self._cache = SchemaCache(ttl=cache_ttl)

        discovery_kwargs = {}
        if resolved_type == "neo4j":
            discovery_kwargs["username"] = username
            discovery_kwargs["password"] = password

        try:
            self._discovery = get_discovery(
                resolved_type, database, **discovery_kwargs
            )
        except Exception as exc:
            raise ConnectionError(
                f"Could not initialize {resolved_type} discovery: {exc}"
            ) from exc

    @staticmethod
    def _detect_db_type(database: str) -> str:
        lower = database.lower()
        if lower.startswith("mongodb://") or lower.startswith("mongodb+srv://"):
            return "mongodb"
        if lower.startswith("bolt://") or lower.startswith("neo4j://"):
            return "neo4j"
        if lower.startswith(("postgresql://", "postgres://", "mysql://")):
            raise ConfigurationError(
                "SQL adapter currently supports SQLite only. "
                "Provide a file path for SQLite."
            )
        return "sqlite"

    # ── Schema ─────────────────────────────────────────────────────────
    def schema(self, refresh: bool = False) -> dict:
        """Return discovered schema metadata.

        Returns a dict with ``collections`` (mapping names to field sets),
        ``ddl`` (human/machine-readable schema text), and ``db_type``.
        """
        if refresh:
            self._cache.invalidate()

        collections = self._cache.get_collections()
        if collections is None:
            try:
                collections = self._discovery.get_collections()
            except Exception as exc:
                raise SchemaError(
                    f"Schema introspection failed for {self.db_type}: {exc}"
                ) from exc
            self._cache.set_collections(collections)

        ddl = self._cache.get_ddl()
        if ddl is None:
            try:
                ddl = self._discovery.get_ddl()
            except Exception as exc:
                raise SchemaError(
                    f"Schema DDL introspection failed for {self.db_type}: {exc}"
                ) from exc
            self._cache.set_ddl(ddl)

        return {
            "db_type": self.db_type,
            "collections": collections,
            "ddl": ddl,
        }

    # ── Query ──────────────────────────────────────────────────────────
    def ask(self, question: str) -> Result:
        """Resolve a natural-language question and execute it read-only."""
        if not question or not question.strip():
            raise IntentResolutionError("Question must not be empty")

        schema_info = self.schema()
        system_prompt = self._build_system_prompt(schema_info["ddl"])

        raw = self._provider.generate_json(
            self._augment_question(question),
            system=system_prompt,
        )

        return self._plan_to_result(raw, question)

    def _augment_question(self, question: str) -> str:
        if not self.metadata:
            return question
        hints = "\n".join(f"- {k}: {v}" for k, v in self.metadata.items())
        return f"Semantic metadata:\n{hints}\n\nQuestion: {question}"

    def _build_system_prompt(self, ddl: str) -> str:
        label = _DB_LABELS.get(self.db_type, "Schema")
        lines = [
            f"You are a database query planner for {self.db_type}.",
            "Output ONLY JSON.",
            f"{label} Schema:",
            ddl,
            "",
            'JSON format: {"action":"SELECT","table":"","columns":[],'
            '"distinct":false,"joins":[],"filters":[],"group_by":[],"having":[],'
            '"aggregations":[],"order_by":[],"limit":null,"offset":null,'
            '"where_logic":"AND","having_logic":"AND"}',
            "",
            "Rules:",
            "- Always include every field.",
            '- action must always be "SELECT" (read-only).',
            "- Never output SQL or explanations.",
        ]
        if self.db_type == "mongodb":
            lines.append('- Use dot notation for nested fields (e.g. "address.city").')
            lines.append('- Set "include_id": false to suppress MongoDB _id.')
        if self.db_type == "neo4j":
            lines.append(
                '- Use "match_patterns" with "labels" and "relationship_types".'
            )
            lines.append('- Use "return_expressions" for graph projection.')
        return "\n".join(lines)

    def _plan_to_result(self, raw: dict, question: str) -> Result:
        """Normalize, validate, and execute a raw LLM plan."""
        # Enforce read-only at the boundary *before* the normalizer silently
        # coerces destructive actions to SELECT. Read-equivalent verbs are
        # tolerated and normalized downstream.
        raw_action = str(raw.get("action", "SELECT")).upper()
        if raw_action not in ("SELECT", "GET", "FETCH", "RETRIEVE", "SHOW", "QUERY", "LIST"):
            if self.read_only:
                raise SafetyError(
                    f"Query action {raw_action!r} blocked by read-only mode."
                )
            raise ValidationError(
                f"Unsupported query action {raw_action!r}."
            )

        normalized = normalize_response(raw, self._discovery, self.db_type)
        normalized["action"] = "SELECT"
        normalized = self._apply_limits(normalized)

        start = time.perf_counter()
        query, params, raw_results = self._execute(normalized)
        execution_time = time.perf_counter() - start

        data, columns = self._normalize_results(raw_results, normalized)
        return Result(
            data=data,
            columns=columns,
            query=query,
            database=self.db_type,
            intent=normalized,
            execution_time=execution_time,
            row_count=len(data),
            metadata={"params": params, "provider": self._provider.name},
            warnings=self._warnings_for(normalized),
            native=raw_results,
        )

    def _apply_limits(self, plan: dict) -> dict:
        if plan.get("limit") is None and self.default_limit is not None:
            plan["limit"] = self.default_limit
        if plan.get("limit") is not None:
            plan["limit"] = min(plan["limit"], self.max_limit)
        return plan

    def _execute(self, plan: dict):
        if self.db_type == "sqlite":
            return build_sql(plan, self.database)
        if self.db_type == "mongodb":
            pipeline, results = build_and_execute_mql(plan, self.database)
            return json.dumps(pipeline, default=str), [], results
        if self.db_type == "neo4j":
            return build_and_execute_cypher(
                plan,
                self.database,
                username=self.config.extra.get("username", ""),
                password=self.config.extra.get("password", ""),
            )
        raise ConfigurationError(f"Unsupported db_type {self.db_type!r}")

    def _normalize_results(self, raw_results, plan: dict):
        if raw_results is None:
            return [], []

        rows = []
        columns = []
        seen_keys = []

        for row in raw_results:
            if isinstance(row, dict):
                clean = dict(row)
                for k, v in clean.items():
                    if hasattr(v, "__str__") and k == "_id":
                        clean[k] = str(v)
                if not columns:
                    columns = list(clean.keys())
                rows.append(clean)
            elif isinstance(row, (list, tuple)):
                rows.append(row)
            else:
                rows.append(row)

        if not rows and plan.get("columns"):
            columns = plan["columns"]

        return rows, columns

    def _warnings_for(self, plan: dict) -> list[str]:
        warnings = []
        if not plan.get("limit") and not self.default_limit:
            warnings.append("No result limit was applied; consider setting default_limit.")
        return warnings

    def invalidate_schema(self) -> None:
        """Force schema re-discovery on the next request."""
        self._cache.invalidate()

    def __repr__(self) -> str:
        return (
            f"QueryAdapter(database={self.database!r}, db_type={self.db_type!r}, "
            f"provider={self._provider.name!r}, read_only={self.read_only})"
        )

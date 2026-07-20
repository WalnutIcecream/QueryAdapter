"""
rosetta — NLP to Database Query Pipeline.

Converts natural language into SQL (SQLite), MQL (MongoDB), or Cypher (Neo4j)
using a two-tier model architecture: T5-small for fast structured queries,
Ollama for conversational chat and fallback.

Quick start:
    from rosetta import run_pipeline

    result = run_pipeline(
        "show customers from New York",
        db_type="sqlite",
        connection_string="path/to/database.db",
    )
    print(result["results"])

For more: https://github.com/WalnutIcecream/NLPtoSQL
"""

from rosetta.app import run_pipeline, build_system_prompt
from rosetta.ir.query_plan import QueryPlan, Filter, Join, Aggregation, OrderBy, MatchPattern
from rosetta.ir.validator import validate_against_schema, SchemaValidationError
from rosetta.nlp.normalizer import normalize_response, strip_json, sanitize_json
from rosetta.nlp.parser import NLPSemParser, get_parser
from rosetta.backends.discovery import get_discovery, BackendDiscovery
from rosetta.conversation.context import ConversationContext, classify_intent

__version__ = "1.0.0"
__all__ = [
    "run_pipeline",
    "build_system_prompt",
    "QueryPlan",
    "Filter",
    "Join",
    "Aggregation",
    "OrderBy",
    "MatchPattern",
    "validate_against_schema",
    "SchemaValidationError",
    "normalize_response",
    "strip_json",
    "sanitize_json",
    "NLPSemParser",
    "get_parser",
    "get_discovery",
    "BackendDiscovery",
    "ConversationContext",
    "classify_intent",
]

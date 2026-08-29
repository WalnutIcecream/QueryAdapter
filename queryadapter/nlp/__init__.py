"""
queryadapter.nlp — Natural Language Processing layer.

Two-tier architecture:
  - Normalizer: normalizes raw LLM/NLP output into the unified IR
  - Parser:   T5-small model for fast text-to-JSON semantic parsing
"""

from queryadapter.nlp.normalizer import (
    normalize_response,
    strip_json,
    sanitize_json,
    get_schema,
    get_schema_ddl,
    parse_expr,
    normalize_filters,
)
from queryadapter.nlp.parser import (
    NLPSemParser,
    get_parser,
)

__all__ = [
    "normalize_response",
    "strip_json",
    "sanitize_json",
    "get_schema",
    "get_schema_ddl",
    "parse_expr",
    "normalize_filters",
    "NLPSemParser",
    "get_parser",
]

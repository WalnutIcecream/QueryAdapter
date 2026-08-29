"""QueryAdapter command-line interface for experimentation and debugging.

Usage:
    queryadapter inspect DATABASE_URL
    queryadapter schema  DATABASE_URL
    queryadapter ask     DATABASE_URL "Which customers spent the most?"
"""

import argparse
import json
import sys
from typing import Optional

from queryadapter import QueryAdapter


def _adapter_from_args(args):
    kwargs = {}
    if getattr(args, "provider", None):
        kwargs["provider"] = args.provider
    if getattr(args, "model", None):
        kwargs["model"] = args.model
    if getattr(args, "api_key", None):
        kwargs["api_key"] = args.api_key
    if getattr(args, "base_url", None):
        kwargs["base_url"] = args.base_url
    if getattr(args, "db_type", None):
        kwargs["db_type"] = args.db_type
    if getattr(args, "user", None):
        kwargs["username"] = args.user
    if getattr(args, "password", None):
        kwargs["password"] = args.password
    return QueryAdapter(args.database, **kwargs)


def cmd_inspect(args) -> int:
    adapter = _adapter_from_args(args)
    schema = adapter.schema(refresh=True)
    print(f"Database type: {schema['db_type']}")
    print(f"Connection:    {args.database}")
    print()
    print("Collections:")
    for name, fields in sorted(schema["collections"].items()):
        print(f"  {name}: {', '.join(sorted(fields)) if fields else '(empty)'}")
    return 0


def cmd_schema(args) -> int:
    adapter = _adapter_from_args(args)
    schema = adapter.schema(refresh=True)
    print(schema["ddl"])
    return 0


def cmd_ask(args) -> int:
    adapter = _adapter_from_args(args)
    result = adapter.ask(args.question)
    print(f"Database: {result.database}")
    print(f"Provider: {result.metadata.get('provider', 'unknown')}")
    print(f"Rows:     {result.row_count}")
    print(f"Query:    {result.query}")
    if result.metadata.get("params"):
        print(f"Params:   {result.metadata['params']}")
    print("Data:")
    for row in result.data:
        print(f"  {row}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="queryadapter",
        description="Natural-language querying for SQL, NoSQL, and graph databases.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("database", help="Path or connection URI")
    common.add_argument(
        "--db-type",
        choices=["sqlite", "mongodb", "neo4j"],
        help="Database type (auto-detected from URI when omitted)",
    )
    common.add_argument("--provider", default="ollama", help="LLM provider")
    common.add_argument("--model", help="Model name override")
    common.add_argument("--api-key", help="API key override")
    common.add_argument("--base-url", help="Provider endpoint override")
    common.add_argument("--user", help="Database username (Neo4j)")
    common.add_argument("--password", help="Database password (Neo4j)")

    p_inspect = sub.add_parser("inspect", parents=[common], help="Show discovered schema")
    p_inspect.set_defaults(func=cmd_inspect)

    p_schema = sub.add_parser("schema", parents=[common], help="Print schema DDL")
    p_schema.set_defaults(func=cmd_schema)

    p_ask = sub.add_parser("ask", parents=[common], help="Ask a natural-language question")
    p_ask.add_argument("question", help="Natural-language question")
    p_ask.set_defaults(func=cmd_ask)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

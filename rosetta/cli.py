"""CLI entry point — `python -m rosetta` or `rosetta` command.

Usage:
    rosetta [db_path] --db-type <sqlite|mongodb|neo4j> [--interactive]

    # Single-shot
    rosetta company.db
    rosetta mongodb://localhost:27017/mydb --db-type mongodb

    # Interactive multi-turn
    rosetta company.db --interactive

    # Interactive with a custom prompt file
    rosetta company.db --prompt my_question.txt

    # List supported backends
    rosetta --backends
"""

import argparse
import os
import sys

from rosetta.app import run_pipeline
from rosetta.backends.discovery import get_discovery
from rosetta.conversation.context import ConversationContext


def load_text(path):
    with open(path) as f:
        return f.read()


def single_shot(db_path, db_type, prompt_path=None, **kwargs):
    """Single-shot mode: reads a prompt file, runs the pipeline, prints results."""
    print(f"Database: {db_path} ({db_type})\n")

    discovery = get_discovery(db_type, db_path, **kwargs)
    print("Schema:")
    print(discovery.get_ddl()[:500])
    print()

    if prompt_path:
        user_prompt = load_text(prompt_path)
    else:
        prompt_file = "prompt.txt"
        if os.path.exists(prompt_file):
            user_prompt = load_text(prompt_file)
        else:
            user_prompt = input("Enter your question: ")

    print(f"Question: {user_prompt}\n")

    result = run_pipeline(user_prompt, db_type, db_path, **kwargs)

    if result["intent"] == "query":
        print(f"Model: {result['model']}  |  Rows: {result['row_count']}")
        print(f"Query: {result['query']}")
        if result["params"]:
            print(f"Params: {result['params']}")
        print("Results:")
        for row in (result["results"] or []):
            print(f"  {row}")
    else:
        print(result["response"])

    print("\nDone.")


def interactive(db_path, db_type, **kwargs):
    """Multi-turn interactive REPL."""
    discovery = get_discovery(db_type, db_path, **kwargs)
    schema_ddl = discovery.get_ddl()

    context = ConversationContext(
        session_id=f"{db_type}_{db_path}",
        db_type=db_type,
        connection_string=db_path,
        schema_ddl=schema_ddl,
        schema_summary=schema_ddl,
    )

    print(f"rosetta [{db_type}] — type 'help' or 'quit'")
    print(f"Schema: {len(schema_ddl)} chars loaded\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        if cmd == "help":
            print("Commands: quit/exit/q, help, schema, history, clear")
            print("Any other text = NLP query or chat question\n")
            continue

        if cmd == "schema":
            print(schema_ddl + "\n")
            continue

        if cmd == "history":
            for t in context.turns[-5:]:
                role = "You" if t.role == "user" else "Bot"
                print(f"  [{t.intent}] {role}: {t.content[:120]}")
            print()
            continue

        if cmd == "clear":
            context.turns.clear()
            print("Conversation history cleared.\n")
            continue

        result = run_pipeline(
            user_input, db_type, db_path, context=context, **kwargs
        )

        if result["intent"] == "query":
            print(f"  [{result['model']}] {result['row_count']} rows")
            for row in (result["results"] or [])[:10]:
                print(f"    {row}")
            if result["row_count"] > 10:
                print(f"    ... {result['row_count'] - 10} more")
        else:
            print(f"  {result['response']}")

        print()


def main():
    parser = argparse.ArgumentParser(
        prog="rosetta",
        description="NLP to Database Query — English to SQL, MQL, or Cypher",
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default=os.environ.get("DB_PATH", "company.db"),
        help="Database path or connection URI",
    )
    parser.add_argument(
        "--db-type", "--db_type",
        default=os.environ.get("DB_TYPE", "sqlite"),
        choices=["sqlite", "mongodb", "neo4j"],
        help="Database type (default: sqlite)",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive multi-turn mode",
    )
    parser.add_argument(
        "-p", "--prompt",
        help="Read question from a file (instead of prompt.txt)",
    )
    parser.add_argument(
        "--user",
        default="",
        help="Username (Neo4j)",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Password (Neo4j)",
    )
    parser.add_argument(
        "--backends",
        action="store_true",
        help="List supported backends and exit",
    )

    args = parser.parse_args()

    if args.backends:
        print("Supported backends:")
        print("  sqlite   — file path, e.g. company.db or /data/app.db")
        print("  mongodb  — URI, e.g. mongodb://host:27017/database")
        print("  neo4j    — URI, e.g. bolt://host:7687 (with --user --password)")
        return

    kwargs = {}
    if args.user:
        kwargs["username"] = args.user
    if args.password:
        kwargs["password"] = args.password

    if args.interactive:
        interactive(args.db_path, args.db_type, **kwargs)
    else:
        single_shot(args.db_path, args.db_type, args.prompt, **kwargs)


if __name__ == "__main__":
    main()

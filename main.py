"""Backward-compatible entry point — delegates to the CLI module.

Usage:
    python main.py [db_path] --db-type <sqlite|mongodb|neo4j> [--interactive]
"""

from rosetta.cli import main

if __name__ == "__main__":
    main()

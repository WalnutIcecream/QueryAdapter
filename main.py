"""Convenience entry point — delegates to the QueryAdapter CLI.

Usage:
    python main.py inspect DATABASE_URL
    python main.py ask DATABASE_URL "Which customers spent the most?"
    python main.py schema DATABASE_URL
"""

from queryadapter.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

# Contributing to QueryAdapter

Thanks for your interest in contributing. QueryAdapter is an embeddable
abstraction layer that lets existing applications query SQL, NoSQL, and graph
databases using natural language. We optimize for correctness, safety, and a
small, predictable public API.

## Getting started

```bash
git clone https://github.com/WalnutIcecream/QueryAdapter.git
cd QueryAdapter
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

## Development workflow

1. Open an issue describing the bug or feature before large changes.
2. Create a branch off `master`.
3. Make focused, minimal changes.
4. Add tests — core IR and validation tests must not require an LLM or
   external database. Use the deterministic fixtures in `tests/conftest.py`.
5. Run the full suite before submitting:

   ```bash
   pytest
   ```

## Conventions

- Public API lives in `queryadapter/__init__.py`; keep it small and stable.
- Database adapters implement the discovery interface in
  `queryadapter/backends/discovery.py` and consume the `QueryPlan` IR from
  `queryadapter/ir/`.
- Providers implement `queryadapter.providers.base.Provider`.
- Prefer deterministic software components over LLM-driven behavior. A prompt
  is never a security boundary.
- Read-only is the default; never bypass safety checks for convenience.

## Extending QueryAdapter

### New database adapter

Implement a discovery adapter and a constructor that consumes the `QueryPlan`
IR, then register it in `QueryAdapter._execute`. The IR, normalizer, and
validator are backend-agnostic and require no changes.

### New LLM provider

```python
from queryadapter.providers import Provider

class MyProvider(Provider):
    name = "myprovider"

    def generate_json(self, prompt, *, system=None, json_schema=None):
        ...

    def generate_text(self, prompt, *, system=None):
        ...
```

Wire it through `queryadapter.providers.create_provider`.

## Release checklist

- All tests pass.
- `README.md` examples are current.
- Optional dependencies in `pyproject.toml` match the code.
- No secrets, credentials, or generated databases are committed.

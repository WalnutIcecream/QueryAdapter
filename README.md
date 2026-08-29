# QueryAdapter

> QueryAdapter lets existing applications query SQL, NoSQL, and graph
> databases using natural language.

```python
from queryadapter import QueryAdapter

adapter = QueryAdapter("path/to/app.db")
result = adapter.ask("Show me the customers who spent the most this year")

print(result.data)       # normalized rows
print(result.query)      # the generated native query
print(result.execution_time)
```

QueryAdapter is **not** a chatbot, a database replacement, or a thin
text-to-SQL wrapper. It is a minimal-configuration, embeddable abstraction
layer: you point it at an existing database, it introspects the schema for
you, and one method call turns a natural-language question into a validated,
read-only native query.

---

## Why QueryAdapter?

The value proposition is engineering, not the novelty of NL querying:

- **Database-agnostic IR** — intent is resolved into a shared intermediate
  representation before it becomes SQL, MQL, or Cypher.
- **Automatic schema discovery** — no manual schema config required.
- **Minimal integration** — one import, one constructor, one method.
- **Validation before execution** — hallucinated fields, unknown tables, and
  unsupported operations are rejected before hitting the database.
- **Read-only by default** — writes are blocked at the execution boundary,
  never by trusting a model prompt.
- **Provider independence** — OpenAI, Anthropic, Ollama, or any
  OpenAI-compatible endpoint.
- **Schema caching and context selection** — metadata is cached and TTL-bound
  so every request doesn't re-introspect or re-send the entire schema.

---

## Installation

```bash
pip install queryadapter
```

The core install includes SQLite and the Ollama provider. Optional extras
cover other databases and providers:

```bash
pip install queryadapter[mongodb]
pip install queryadapter[neo4j]
pip install queryadapter[openai]
pip install queryadapter[anthropic]
pip install queryadapter[all]
```

---

## Quick Start

### Python API

```python
from queryadapter import QueryAdapter

# SQLite (auto-detected from the file path)
adapter = QueryAdapter("company.db")
result = adapter.ask("Which customers spent the most?")
print(result.data)

# MongoDB (auto-detected from the URI)
adapter = QueryAdapter("mongodb://localhost:27017/ecommerce")
result = adapter.ask("Show products under $50 in Electronics")

# Neo4j (auto-detected from bolt://)
adapter = QueryAdapter(
    "bolt://localhost:7687",
    username="neo4j",
    password="secret",
)
result = adapter.ask("Find customers who bought Electronics")
```

### CLI

```bash
queryadapter inspect DATABASE_URL
queryadapter schema  DATABASE_URL
queryadapter ask     DATABASE_URL "Which customers spent the most?"
```

---

## Configuration

Everything works with sensible defaults; configure only what you need.

```python
QueryAdapter(database)                          # minimal

QueryAdapter(
    database,
    provider="openai",                          # openai | anthropic | ollama
    model="gpt-4o-mini",
    api_key="...",                              # or read from env
)

QueryAdapter(
    database,
    read_only=True,                             # default
    metadata={
        "orders.amount": "Total order value in INR",
        "users.status": "1=active, 2=suspended, 3=deleted",
    },
)

QueryAdapter(
    database,
    default_limit=50,                           # apply when no LIMIT present
    max_limit=1000,                             # hard ceiling on every query
)
```

Semantic metadata is **optional** — automatic introspection is the default,
and metadata only augments what was discovered.

### Provider API keys

Providers read keys from the environment when `api_key` is omitted:

| Provider | Environment variable |
|---|---|
| OpenAI / compatible | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Ollama | none (local server) |

Any LLM can be wired in by passing a `base_url` for OpenAI-compatible
endpoints, or by subclassing `queryadapter.providers.Provider`.

---

## The Result Object

Every `ask()` call returns a `Result`:

```python
result.data          # normalized rows/documents
result.columns       # column names (tabular backends)
result.query         # generated SQL / pipeline / Cypher
result.database      # "sqlite" | "mongodb" | "neo4j"
result.intent        # the resolved database-agnostic IR
result.execution_time
result.row_count
result.metadata      # params, provider, extra
result.warnings      # non-fatal diagnostics
result.native        # raw backend result, when available
```

Graph results are preserved as node/relationship records rather than forcibly
flattened into rows.

---

## Architecture

```
Natural Language
        |
        v
Intent Understanding (provider)
        |
        v
Database-Agnostic IR (QueryPlan)
        |
        v
Validation / Resolution
        |
        v
Database Adapter
   /       |       \
 SQL     NoSQL    Graph
   \       |       /
Native Query
        |
        v
Execution (read-only)
        |
        v
Structured Result
```

The LLM is **one component** in the pipeline, not the architecture itself.
SQL is **one adapter**, not the center. The IR (`QueryPlan`) is what lets the
same intent compile to SQL, a MongoDB aggregation pipeline, or Cypher.

### Package layout

```
queryadapter/
    core.py            QueryAdapter facade
    config.py          QueryAdapterConfig
    result.py          Result
    errors.py          typed error hierarchy
    cache.py           TTL schema cache
    ir/                QueryPlan IR + schema validator
    nlp/               normalizer + (optional) T5 parser
    backends/          SQLite, MongoDB, Neo4j adapters + discovery
    providers/         Provider abstraction + implementations
    conversation/      multi-turn context + intent routing
    cli.py             inspect / ask / schema
```

---

## Supported Databases

| Backend | Introspection | Query generation | Execution |
|---|---|---|---|
| SQLite | tables, columns, PKs, inferred FKs | parameterized SQL | yes |
| MongoDB | collections, sampled fields, nested types | aggregation pipeline | yes |
| Neo4j | labels, relationship types, properties | Cypher | yes |

Additional SQL dialects (PostgreSQL, MySQL) can be added by implementing a
discovery adapter and a constructor — the IR, normalizer, and validator are
already backend-agnostic.

---

## Safety

- **Read-only by default.** `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `UPDATE`,
  and `INSERT` are blocked before execution. Prompts are never treated as a
  security boundary.
- **Schema whitelisting.** Tables, columns, labels, and relationship types are
  checked against live introspection before a query runs.
- **Parameterized values.** Values are bound as parameters, never concatenated
  into queries.
- **Operator and function whitelists** prevent injection of arbitrary syntax.
- **No secret logging.** Credentials are not emitted in results or errors.

Set `read_only=False` only when you explicitly need writes, and understand
that this moves validation responsibility onto your own policy layer.

---

## Reliability and Testing

The test suite covers IR round-tripping, schema validation, safety blocking,
provider JSON extraction, SQL generation, Cypher generation, caching, and
end-to-end flows with a deterministic mock provider. Core IR and validation
tests do **not** require an LLM or external services.

```bash
pip install -e ".[test]"
pytest
```

---

## Extending QueryAdapter

### New database adapter

Implement the discovery interface in `queryadapter/backends/discovery.py` and a
constructor that consumes the `QueryPlan` IR, then register it in
`QueryAdapter._execute`. The core system needs no changes.

### Custom provider

```python
from queryadapter.providers import Provider

class MyProvider(Provider):
    name = "myprovider"

    def generate_json(self, prompt, *, system=None, json_schema=None):
        ...

    def generate_text(self, prompt, *, system=None):
        ...
```

Then pass it via `create_provider("myprovider", ...)` or subclass
`QueryAdapter`.

---

## Known Limitations

- SQL support is currently SQLite only; PostgreSQL/MySQL adapters are the
  natural next step and the IR already supports joins/aggregates/temporals.
- Neo4j graph query generation supports the IR's `match_patterns` and
  `return_expressions` fields, with a relational fallback from `table`/`joins`.
- T5-small remains available in `queryadapter.nlp.parser` for local structured
  parsing but is not the default provider path.

---

## License

MIT

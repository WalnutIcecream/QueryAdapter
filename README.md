# Rosetta

> *"Like its namesake, Rosetta sits between people and their data, translating
> human language into the native tongues of databases—SQL, MQL, Cypher. The
> original Rosetta Stone took scholars twenty years to crack a single script.
> This one does three backends in ~20ms."*

**Natural language → SQL · MQL · Cypher.**

A Python package that converts English questions into database queries across
three backends—SQLite, MongoDB, and Neo4j—using a two-tier NLP architecture:
a fast encoder-decoder model for structured queries, and a conversational LLM
for chat and follow-ups.

```
$ rosetta /var/data/app.db --interactive

> show customers from New York with orders over $500
  [t5-small] 3 rows
    ('Alice Johnson', 'New York')
    ...
```

---

## Architecture

```
                         ┌──────────────────────┐
                         │     User message     │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼────────────┐
                         │    Intent Router      │
                         └──────────┬────────────┘
                                    │
                    query ──────────┼────────── chat
                    ┌───────────────┼───────────────┐
                    │                               │
           ┌────────▼────────┐            ┌─────────▼─────────┐
           │   T5-small       │           │  Ollama           │
           │   60M params     │           │  llama3.2:3b      │
           │   ~20 ms CPU     │           │  ~1000 ms CPU     │
           │   structured     │           │  conversational   │
           └────────┬────────┘            └─────────┬─────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │ JSON IR
                         ┌──────────▼────────────┐
                         │     Normalizer        │
                         │     Validator         │
                         └──────────┬────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │  SQLite  │  │ MongoDB  │  │  Neo4j   │
              │    SQL   │  │   MQL    │  │  Cypher  │
              └──────────┘  └──────────┘  └──────────┘
```

The pipeline is backend-agnostic. The NLP model produces a common JSON
**Intermediate Representation** (IR) that is validated against the live
database schema, then dispatched to the appropriate query constructor. Adding
PostgreSQL or MySQL requires only a new backend module.

---

## Installation

```bash
git clone https://github.com/WalnutIcecream/Rosetta.git
cd Rosetta

# Core: Ollama only (works immediately)
pip install -e .

# Everything: T5 model + MongoDB + Neo4j drivers
pip install -e ".[all]"
```

**Requirements:**

- Python ≥ 3.11
- [Ollama](https://ollama.com) (local LLM runtime)
- `ollama pull llama3.2:3b` (or any model; hardcoded in `rosetta/app.py`)

Optional:
- `transformers` + `torch` — enables T5-small (40× faster than Ollama for structured queries)
- `pymongo` — MongoDB backend
- `neo4j` — Neo4j driver

---

## Quick Start

### CLI

```bash
# Single-shot (reads prompt.txt)
echo "show customers from New York" > prompt.txt
rosetta my_database.db

# Interactive REPL
rosetta my_database.db --interactive

# MongoDB
rosetta mongodb://localhost:27017/ecommerce --db-type mongodb -i

# Neo4j (graph enabled, Cypher stub)
rosetta bolt://localhost:7687 --db-type neo4j --user neo4j --password secret -i

# List supported backends
rosetta --backends
```

### Python API

```python
from rosetta import run_pipeline, ConversationContext

# One-shot query
result = run_pipeline(
    "show customers from New York with orders over $500",
    db_type="sqlite",
    connection_string="path/to/database.db",
)
print(result["results"])   # list of rows
print(result["query"])     # the SQL that executed
print(result["model"])     # "t5-small" or "ollama"

# Multi-turn conversation
ctx = ConversationContext("session_1", "sqlite", "path/to/db")

r1 = run_pipeline("show products under $50", context=ctx)
r2 = run_pipeline("how many of them are in Electronics?", context=ctx)
# r2 automatically carries forward prior table + filter context
```

### Embed in a Web Application

```python
from fastapi import FastAPI
from rosetta import run_pipeline, ConversationContext

app = FastAPI()
sessions = {}

@app.post("/query")
def query(user_id: str, question: str, db_path: str):
    ctx = sessions.get(user_id)
    if ctx is None:
        ctx = ConversationContext(user_id, "sqlite", db_path)
        sessions[user_id] = ctx
    result = run_pipeline(question, db_type="sqlite",
                          connection_string=db_path, context=ctx)
    return {"results": result["results"], "query": result["query"]}
```

---

## Package Structure

```
Rosetta/
├── cli.py                              # Entry point for `rosetta` command
├── main.py                             # Backward-compat: delegates to cli.py
├── pyproject.toml                      # PEP 621 metadata, dependencies
├── requirements.txt                    # Minimal: ollama only
│
├── rosetta/                            # Installable package
│   ├── __init__.py                     # Public API surface (20 exports)
│   ├── app.py                          # Pipeline orchestrator
│   │
│   ├── ir/                             # Intermediate Representation
│   │   ├── __init__.py
│   │   ├── query_plan.py               #   QueryPlan, Filter, Join, etc.
│   │   └── validator.py                #   Schema validation + security
│   │
│   ├── nlp/                            # Natural Language Processing
│   │   ├── __init__.py
│   │   ├── normalizer.py               #   Raw LLM output → canonical IR
│   │   └── parser.py                   #   T5-small loading / inference
│   │
│   ├── backends/                       # Database query constructors
│   │   ├── __init__.py
│   │   ├── discovery.py                #   Schema discovery interface
│   │   ├── sqlite.py                   #   SQL builder (full)
│   │   ├── mongodb.py                  #   MQL pipeline builder (full)
│   │   └── neo4j.py                   #   Cypher constructor (stub)
│   │
│   └── conversation/                   # Multi-turn context
│       ├── __init__.py
│       └── context.py                  #   Intent router + history
│
└── demos/                              # Self-contained demos
    ├── run_demo.py                     #   Full pipeline demo
    ├── sql/setup_db.py                 #   Seed a SQLite test database
    ├── mongo/setup_db.py               #   Seed a MongoDB test database
    └── neo4j/setup_db.py              #   Seed a Neo4j test graph
```

---

## Inside Each Module

### `rosetta/app.py` — Pipeline Orchestrator

`run_pipeline(user_query, db_type, connection_string, context, **kwargs)`

The central function. Accepts natural language, discovers the schema from the
live database, routes to T5 or Ollama based on intent, normalizes the output
into an IR, validates it against the schema, dispatches to the backend
constructor, executes the query, and stores the turn in the conversation
context.

### `rosetta/ir/query_plan.py` — Intermediate Representation

Defines the canonical data structures that every backend consumes:

| Class | Fields | Purpose |
|---|---|---|
| `QueryPlan` | `action`, `table`, `columns`, `joins`, `filters`, `group_by`, `having`, `aggregations`, `order_by`, `limit`, `offset`, `where_logic`, `having_logic`, `distinct`, `db_type`, `unwind`, `include_id`, `match_patterns`, `return_expressions` | Top-level query plan |
| `Filter` | `column`, `operator`, `value` | WHERE / $match / WHERE predicate |
| `Join` | `type`, `table`, `on` | SQL JOIN / $lookup / MATCH |
| `Aggregation` | `function`, `column`, `alias` | COUNT / SUM / AVG / MIN / MAX |
| `OrderBy` | `column`, `direction` | ASC / DESC |
| `MatchPattern` | `variable`, `labels`, `relationship_types`, `direction`, `min_hops`, `max_hops`, `optional`, `properties`, `from_variable`, `to_variable` | Neo4j graph pattern |

The IR round-trips through `to_dict()` / `from_dict()` and is validated
structurally by `validate_plan_structure()`.

### `rosetta/ir/validator.py` — Schema Validator

`validate_against_schema(plan, tables)`

The security gate. Runs before any query executes:

1. **Blocks non-SELECT actions.** INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
   TRUNCATE are rejected with `SchemaValidationError`.
2. **Whitelists table/column names.** Every table, column, and join target is
   checked against the live schema. References to non-existent objects are
   rejected—this prevents hallucinated columns from reaching the database.
3. **Validates identifiers.** Regex `^[a-zA-Z_][a-zA-Z0-9_]*$` (with dot
   notation for MongoDB nested fields). Blocks injection attempts like
   `name; DROP TABLE--`.
4. **Whitelists operators.** Only `= != <> > < >= <= LIKE IN NOT IN IS IS NOT
   BETWEEN` pass. `EXEC`, `SCRIPT`, or any unknown operator string is rejected.
5. **Whitelists aggregate functions.** Only `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`.
6. **Sanitizes logic combinators.** `where_logic` and `having_logic` are forced
   to `AND` or `OR`.
7. **Validates limit/offset.** Must be non-negative integers or null.

### `rosetta/nlp/normalizer.py` — Output Normalizer

`normalize_response(raw_llm_data, db_path_or_discovery, db_type)`

Takes the raw dict from the NLP model (which may have variant key names,
unnormalized values, missing fields, or expression strings) and produces a
canonical IR. Key functions:

| Function | Purpose |
|---|---|
| `strip_json(s)` | Strips markdown fences from LLM output |
| `sanitize_json(s)` | Removes trailing commas, balances braces/brackets |
| `parse_expr(s)` | Parses `"salary > 10000"` into `{column, operator, value}` |
| `normalize_filters(filters)` | Handles string→dict conversion, condition type mapping, IS NULL/BETWEEN/IN/OR |
| `normalize_joins(joins, main, discovery)` | Normalizes join objects, auto-infers ON clauses |
| `infer_missing_joins(data, tables, discovery)` | Detects when columns reference other tables and adds JOINs |
| `qualify_columns(data, tables)` | Prepends table prefixes to unqualified column names |
| `normalize_response(raw, db_path, db_type)` | Master function: calls all of the above + validates |

### `rosetta/nlp/parser.py` — T5-small Semantic Parser

`NLPSemParser(model_name="t5-small")`

A dedicated encoder-decoder model for text-to-JSON. 60M parameters, ~20 ms
inference on CPU—approximately **40–50× faster** than llama3.2:3b for
structured output.

- **`parse(user_query, schema_ddl)`** — Converts NL → JSON query plan. Returns
  `None` if unavailable (caller falls back to Ollama).
- **`train(train_pairs, output_dir)`** — Fine-tunes on custom (NL, schema,
  JSON) triples using HuggingFace `Seq2SeqTrainer`.
- **`available`** — Boolean: `True` if `transformers` + `torch` are installed.
- **`get_parser()`** — Global singleton.

If `transformers` is not installed, the system degrades gracefully: all
structured queries route through Ollama instead—slower, but fully functional.

### `rosetta/backends/discovery.py` — Schema Discovery

`get_discovery(db_type, connection_string)` → `BackendDiscovery`

Factory function. Returns a backend-specific discovery adapter implementing:

| Method | SQLite | MongoDB | Neo4j |
|---|---|---|---|
| `get_collections()` | `sqlite_master` + `PRAGMA table_info` | Samples 10 docs per collection | `CALL db.labels()` + node sampling |
| `get_ddl()` | `CREATE TABLE` SQL | Rendered field-per-collection summary | `CALL db.schema.visualization()` |
| `infer_relationships(main, target)` | `{singlular}_id` naming convention | Looks for `{collection}_id` fields | Returns `{}` (handled by `edges` in IR) |

### `rosetta/backends/sqlite.py` — SQL Constructor

`build_and_execute(plan, db_path)` → `(query, params, rows)`

Produces parameterized SQL (`?` placeholders). Supports:

- SELECT, DISTINCT
- JOINs (INNER, LEFT, RIGHT) with auto-inferred ON clauses
- WHERE with AND/OR logic, IS NULL, BETWEEN, IN, NOT IN, LIKE
- GROUP BY, HAVING
- ORDER BY with ASC/DESC
- LIMIT, OFFSET

### `rosetta/backends/mongodb.py` — MQL Constructor

`build_mql_pipeline(plan)` → `list[dict]`

Produces a MongoDB aggregation pipeline. Stage order:

```
$match → $lookup → $unwind → $group → $match(havING) → $project → $sort → $skip → $limit
```

Operator mappings:

| IR operator | MQL operator |
|---|---|
| `=` | `$eq` |
| `!=` | `$ne` |
| `>` | `$gt` |
| `<` | `$lt` |
| `>=` | `$gte` |
| `<=` | `$lte` |
| `IN` | `$in` |
| `NOT IN` | `$nin` |
| `IS` | `$eq: null` |
| `IS NOT` | `$ne: null` |
| `BETWEEN` | `$gte` + `$lte` |
| `LIKE` | `$regex` |

Handles nested documents (`address.city`), `$unwind` for array flattening,
`_id` suppression, and `$lookup` + `$unwind` for JOIN-equivalent queries.

### `rosetta/conversation/context.py` — Conversation Manager

`ConversationContext(session_id, db_type, connection_string)`

- Stores up to 15 `ConversationTurn` entries (user message, query plan,
  executed query, result preview).
- `classify_intent(user_input, context)` — heuristic router:
  `show/find/count/…` → `"query"` (T5), `explain/describe/help/…` → `"chat"` (Ollama).
- `resolve_follow_up(user_input)` — detects pronouns (`them`, `those`, `it`)
  and injects the previous query's table + filter context into the prompt.
- `build_chat_prompt(user_input)` — enriches the Ollama prompt with schema
  summary + conversation history + result previews.
- `build_query_prompt(user_input)` — enriches the T5 prompt with follow-up
  context.

---

## Supported SQL Features (all backends)

| Feature | SQLite | MongoDB | Neo4j |
|---|---|---|---|
| SELECT / find | ✓ | ✓ | stub |
| WHERE / $match / WHERE | ✓ | ✓ | stub |
| AND / OR logic | ✓ | ✓ | stub |
| IS NULL / IS NOT NULL | ✓ | ✓ | stub |
| BETWEEN | ✓ | ✓ | stub |
| IN / NOT IN | ✓ | ✓ | stub |
| LIKE / $regex | ✓ | ✓ | stub |
| JOIN / $lookup / MATCH | ✓ | ✓ | stub |
| GROUP BY / $group / RETURN | ✓ | ✓ | stub |
| HAVING / post-$group $match | ✓ | ✓ | stub |
| ORDER BY / $sort | ✓ | ✓ | stub |
| LIMIT / $limit | ✓ | ✓ | stub |
| OFFSET / $skip | ✓ | ✓ | stub |
| DISTINCT | ✓ | ✓ | stub |
| Nested fields (`address.city`) | — | ✓ | — |
| Array unwinding ($unwind) | — | ✓ | — |
| Graph traversal patterns | — | — | IR defined |
| Variable-length paths | — | — | IR defined |
| Relationship properties | — | — | IR defined |

---

## Security

**Read-only by design.** Every query plan is forced to `action: "SELECT"`.
`SchemaValidationError` is raised for any non-SELECT action.

**No blind injection.** Table names, column names, operators, and aggregate
functions are validated against a live-schema whitelist before string
interpolation. Invalid identifiers are blocked by regex.

**Parameterized values.** All user/LLM-supplied values use `?` placeholders
(SQLite) or MongoDB's type-safe operators. No values are ever string-concatenated
into SQL.

---

## Performance

| Model | Parameters | CPU latency (per query) | Use case |
|---|---|---|---|
| T5-small | 60M | ~20 ms | Structured queries (~85% of traffic) |
| Ollama llama3.2:3b | 3B | ~800–1200 ms | Chat, explanations, fallback (~15%) |

T5-small is 40–50× faster than llama3.2:3b for this structured-output task.
The model is optional—if `transformers` is not installed, the system falls
back to Ollama automatically.

---

## Adding a New Backend

1. **Schema discovery.** Subclass `BackendDiscovery` in `rosetta/backends/discovery.py`
   and implement `get_collections()`, `get_ddl()`, `infer_relationships()`.

2. **Query constructor.** Create `rosetta/backends/postgresql.py` with a
   `build_and_execute(plan, connection_string)` function that consumes a
   `QueryPlan` and returns `(query, params, rows)`.

3. **Wire it in.** Add the backend to `_execute_query()` in
   `rosetta/app.py`, register the CLI choice in `cli.py`, and add the driver
   to `pyproject.toml` optional dependencies.

The IR, normalizer, validator, and conversation context are backend-agnostic
and require no changes.

---

## Demo

```bash
cd demos
python run_demo.py
```

Runs without external servers—creates a temporary SQLite database, generates
MongoDB aggregation pipelines in memory, and shows Neo4j graph patterns.
Demonstrates: schema discovery, query normalization, SQL generation, MQL
pipeline construction, Neo4j IR mapping, intent routing, and follow-up
resolution.

---

## License

MIT

---

## Contributing

Bug reports and pull requests are welcome. The primary extension points are:

- **Backends.** Adding a new database backend.
- **NLP models.** Swapping T5 for CodeT5, fine-tuning on domain data, or
  adding ONNX Runtime for further speedups.
- **Neo4j Cypher.** Completing the Cypher constructor from the existing
  `match_patterns` + `return_expressions` IR fields.

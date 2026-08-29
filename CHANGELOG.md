# Changelog

All notable changes to QueryAdapter are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-08-29

### Added

- `QueryAdapter` facade with a minimal `ask()` integration.
- Database-agnostic `QueryPlan` intermediate representation.
- Automatic schema introspection for SQLite, MongoDB, and Neo4j.
- SQL (SQLite) query generation and execution.
- MongoDB aggregation pipeline generation and execution.
- Neo4j Cypher generation and execution.
- Pluggable provider abstraction: Ollama, OpenAI, Anthropic, and
  OpenAI-compatible endpoints.
- Read-only safety enforcement at the execution boundary.
- Schema validation and typed, actionable error hierarchy.
- TTL-based schema caching.
- CLI (`queryadapter inspect|schema|ask`).
- Deterministic test suite covering IR, validation, adapters, providers,
  safety, caching, and end-to-end flows.

"""Application layer (rosetta.app).

Entry point for the NLP-to-database pipeline. Wires together:
  - Schema discovery via backends
  - Two-tier model routing (T5-small NLP / Ollama conversational)
  - Query plan normalization and validation
  - Backend-specific query execution
  - Multi-turn conversation context

Usage:
    from rosetta import run_pipeline

    result = run_pipeline(
        "show customers from New York",
        db_type="sqlite",
        connection_string="path/to/database.db",
    )

    # result = {
    #     "results": [...],
    #     "query": "SELECT ...",
    #     "params": [...],
    #     "intent": "query",
    #     "row_count": 5,
    #     "model": "t5-small" | "ollama",
    #     "plan": {...},
    # }
"""

import json

import ollama

from rosetta.nlp.normalizer import strip_json, sanitize_json, normalize_response
from rosetta.nlp.parser import get_parser
from rosetta.backends.discovery import get_discovery
from rosetta.backends.sqlite import build_and_execute as build_sql
from rosetta.backends.mongodb import build_and_execute_mql
from rosetta.backends.neo4j import build_and_execute_cypher
from rosetta.conversation.context import ConversationContext, classify_intent


def build_system_prompt(discovery, db_type):
    """Build the system prompt for the Ollama LLM from live schema."""
    ddl_text = discovery.get_ddl()

    labels = {"sqlite": "SQL", "mongodb": "MQL", "neo4j": "Cypher"}
    schema_label = labels.get(db_type, "Schema")

    prompt = f"""You are a database query planner for {db_type}.

Output ONLY JSON.

{schema_label} Schema:

{ddl_text}

JSON format:

{{
  "action": "",
  "table": "",
  "columns": [],
  "distinct": false,
  "joins": [],
  "filters": [],
  "group_by": [],
  "having": [],
  "aggregations": [],
  "order_by": [],
  "limit": null,
  "offset": null
}}

Rules:
- Always include every field
- Never output SQL or other code
- Never output explanations
- action must always be "SELECT" (read-only queries only)
- Use "where_logic": "OR" when multiple filters should use OR instead of AND
"""
    if db_type == "mongodb":
        prompt += "- Use dot notation for nested fields (e.g., 'address.city')\n"
        prompt += '- Set "include_id": false to suppress MongoDB _id in results\n'

    return prompt


def _execute_query(plan, conn_string, db_type):
    """Route a normalized query plan to the appropriate backend."""
    if db_type == "sqlite":
        return build_sql(plan, conn_string)
    elif db_type == "mongodb":
        pipeline, results = build_and_execute_mql(plan, conn_string)
        return json.dumps(pipeline, default=str), [], results
    elif db_type == "neo4j":
        return build_and_execute_cypher(plan, conn_string)
    else:
        raise ValueError(f"Unsupported db_type: {db_type!r}")


def _format_results(results, limit=20):
    """Format query results for display."""
    if not results:
        return []
    items = []
    for row in results[:limit]:
        if isinstance(row, dict):
            if "_id" in row and hasattr(row["_id"], "__str__"):
                row = dict(row)
                row["_id"] = str(row["_id"])
            items.append(row)
        else:
            items.append(row)
    return items


def run_pipeline(
    user_query,
    db_type="sqlite",
    connection_string="company.db",
    context=None,
    **kwargs,
):
    """Run the full NLP-to-query pipeline for a single user message.

    Args:
        user_query: Natural language question.
        db_type: "sqlite", "mongodb", or "neo4j".
        connection_string: Database path or connection URI.
        context: Existing ConversationContext (None = new session).
        **kwargs: Extra backend params (username, password for Neo4j).

    Returns:
        dict with keys: results, query, params, intent, row_count, model, plan
    """
    discovery = get_discovery(db_type, connection_string, **kwargs)
    schema_ddl = discovery.get_ddl()

    if context is None:
        context = ConversationContext(
            session_id=f"{db_type}_{connection_string}",
            db_type=db_type,
            connection_string=connection_string,
            schema_ddl=schema_ddl,
            schema_summary=schema_ddl,
        )

    intent = classify_intent(user_query, context)
    context.add_turn("user", user_query, intent=intent)

    if intent == "query":
        nlp_parser = get_parser()
        llm_data = None
        used_model = "ollama"

        if nlp_parser.available:
            resolved = context.build_query_prompt(user_query)
            llm_data = nlp_parser.parse(resolved, schema_ddl)
            if llm_data:
                used_model = "t5-small"

        if llm_data is None:
            system_prompt = build_system_prompt(discovery, db_type)
            deep_context = context.build_query_prompt(user_query)
            resp = ollama.generate(
                model="llama3.2:3b",
                system=system_prompt,
                prompt=deep_context,
            )
            cleaned = sanitize_json(strip_json(resp["response"]))
            llm_data = json.loads(cleaned)

        normalized = normalize_response(llm_data, connection_string, db_type)
        query, params, raw_results = _execute_query(
            normalized, connection_string, db_type
        )
        results = _format_results(raw_results)

        context.add_turn(
            "assistant",
            f"Query executed ({len(raw_results)} rows)",
            intent="query",
            json_plan=normalized,
            query_executed=query,
            results=raw_results,
        )

        return {
            "results": results,
            "query": query,
            "params": params,
            "intent": "query",
            "row_count": len(raw_results),
            "model": used_model,
            "plan": normalized,
        }

    else:
        chat_prompt = context.build_chat_prompt(user_query)
        system_prompt = build_system_prompt(discovery, db_type)
        system_prompt += (
            "\n\nYou are a helpful data assistant. Answer questions "
            "about the database schema, explain results, and help "
            "users form queries."
        )

        resp = ollama.generate(
            model="llama3.2:3b",
            system=system_prompt,
            prompt=chat_prompt,
        )
        response = resp["response"]

        context.add_turn("assistant", response, intent="chat")

        return {
            "results": None,
            "query": None,
            "params": None,
            "intent": "chat",
            "response": response,
            "model": "ollama",
            "plan": None,
        }

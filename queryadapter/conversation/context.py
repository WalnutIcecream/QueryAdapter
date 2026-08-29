"""Conversation context manager with intent routing and multi-turn history.

Manages multi-turn conversations where users can ask data queries, follow up
with refinements, and ask contextual questions about results.

Two-tier routing:
  - 'query' → T5-small NLP model (fast, structured JSON output)
  - 'chat'  → Ollama conversational LLM (explanations, help, result discussion)
"""

import time
from dataclasses import dataclass, field
from typing import Optional


QUERY_KEYWORDS = [
    "show", "find", "list", "get", "count", "how many",
    "average", "sum", "total", "who", "which", "what are",
    "give me", "display", "fetch", "retrieve", "calculate",
    "aggregate", "group by", "sort", "order", "filter",
]

CHAT_KEYWORDS = [
    "explain", "what does", "how does", "why", "help",
    "what is a", "tell me about", "describe", "compare",
    "what tables", "what columns", "what database", "schema",
]

REFERENCE_KEYWORDS = ["that", "those", "it", "them", "this", "the result",
                       "the results", "why are", "how many of them"]


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    turn_id: int
    role: str                    # "user" | "assistant"
    content: str                 # raw text
    intent: str                  # "query" | "chat"
    json_plan: Optional[dict] = None
    query_executed: Optional[str] = None
    result_preview: Optional[str] = None
    result_row_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationContext:
    """Tracks a multi-turn conversation session.

    Stores conversation history, schema context, and provides methods
    for building enriched prompts that inject prior query results.
    """
    session_id: str
    db_type: str
    connection_string: str
    schema_ddl: str = ""
    schema_summary: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    max_turns: int = 15

    @property
    def last_result(self) -> Optional[str]:
        """The preview text of the most recent query result, if any."""
        for turn in reversed(self.turns):
            if turn.result_preview:
                return turn.result_preview
        return None

    @property
    def last_plan(self) -> Optional[dict]:
        """The query plan of the most recent query, if any."""
        for turn in reversed(self.turns):
            if turn.json_plan is not None:
                return turn.json_plan
        return None

    def add_turn(
        self,
        role: str,
        content: str,
        intent: str = "chat",
        json_plan: Optional[dict] = None,
        query_executed: Optional[str] = None,
        results: Optional[list] = None,
    ):
        """Record a conversation turn."""
        preview = None
        row_count = 0
        if results:
            row_count = len(results)
            preview = str(results[:5]) if len(results) > 5 else str(results)

        self.turns.append(ConversationTurn(
            turn_id=len(self.turns),
            role=role,
            content=content,
            intent=intent,
            json_plan=json_plan,
            query_executed=query_executed,
            result_preview=preview,
            result_row_count=row_count,
        ))

        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def resolve_follow_up(self, user_input: str) -> str:
        """Detect follow-up references and inject prior query context.

        If the user says "how many of them are in Engineering?" after
        querying employees, this detects "them" and augments the input
        with the previous query's table and filters.
        """
        lower = user_input.lower()
        has_reference = any(w in lower for w in REFERENCE_KEYWORDS)

        if not has_reference or not self.last_plan:
            return user_input

        prior = self.last_plan
        context_parts = []

        table = prior.get("table", "")
        if table:
            context_parts.append(f"previous query was on table '{table}'")

        filters = prior.get("filters", [])
        if filters:
            filter_str = ", ".join(
                f"{f.get('column', '?')} {f.get('operator', '=')} {f.get('value', '?')}"
                for f in filters
            )
            context_parts.append(f"with filters: {filter_str}")

        joins = prior.get("joins", [])
        if joins:
            join_names = [j.get("table", "?") for j in joins]
            context_parts.append(f"joined with: {', '.join(join_names)}")

        if context_parts:
            augmented = f"({'; '.join(context_parts)}). Now: {user_input}"
            return augmented

        return user_input

    def build_chat_prompt(self, user_input: str) -> str:
        """Build an enriched prompt for the conversational LLM.

        Includes schema summary and recent conversation history.
        """
        blocks = []

        if self.schema_summary:
            blocks.append(f"[DATABASE SCHEMA]\n{self.schema_summary}")

        if self.turns:
            history_lines = []
            for turn in self.turns[-8:]:
                if turn.role == "user":
                    history_lines.append(f"User: {turn.content}")
                elif turn.intent == "query" and turn.result_preview:
                    history_lines.append(
                        f"Assistant [query]: {turn.result_row_count} rows returned. "
                        f"Preview: {turn.result_preview}"
                    )
                else:
                    history_lines.append(f"Assistant: {turn.content}")
            blocks.append("[CONVERSATION]\n" + "\n".join(history_lines))

        blocks.append(f"[QUESTION]\n{user_input}")
        return "\n\n".join(blocks)

    def build_query_prompt(self, user_input: str) -> str:
        """Build a prompt for the NLP model, including follow-up context."""
        resolved = self.resolve_follow_up(user_input)
        return resolved

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "db_type": self.db_type,
            "connection_string": self.connection_string,
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "role": t.role,
                    "content": t.content,
                    "intent": t.intent,
                    "query_executed": t.query_executed,
                    "result_row_count": t.result_row_count,
                }
                for t in self.turns
            ],
        }


def classify_intent(user_input: str, context: Optional[ConversationContext] = None) -> str:
    """Route user input to 'query' (T5 NLP model) or 'chat' (Ollama LLM).

    Returns:
        'query' — structured data query, use fast NLP model
        'chat'  — explanation, help, or result discussion, use conversational LLM
    """
    lower = user_input.lower().strip()

    # Explicit follow-up questions about results → chat
    if context and context.last_result:
        if any(w in lower for w in REFERENCE_KEYWORDS):
            if any(w in lower for w in ["why", "explain", "what does", "how does"]):
                return "chat"

    # Meta/schema questions → chat
    if any(w in lower for w in ["table", "column", "schema", "field", "database"]):
        if any(w in lower for w in ["explain", "describe", "what", "tell", "show table", "show tables"]):
            return "chat"

    # Help/intro questions → chat
    if lower in ("help", "hello", "hi", "what can you do"):
        return "chat"

    # Structured query keywords → query
    if any(kw in lower for kw in QUERY_KEYWORDS):
        return "query"

    # Chat/explanation keywords → chat
    if any(kw in lower for kw in CHAT_KEYWORDS):
        return "chat"

    # Default: try query first (cheap T5), let fallback handle failures
    return "query"

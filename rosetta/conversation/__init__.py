"""
rosetta.conversation — Multi-turn conversation context and intent routing.

Routes user input to either the fast NLP model (for structured queries)
or the conversational LLM (for chat/explanations). Manages multi-turn
history so follow-up questions can reference prior query results.
"""

from rosetta.conversation.context import (
    ConversationContext,
    ConversationTurn,
    classify_intent,
)

__all__ = [
    "ConversationContext",
    "ConversationTurn",
    "classify_intent",
]

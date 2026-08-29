"""Shared helpers for provider implementations."""

import json
import re

from queryadapter.errors import ProviderError


def extract_json(text: str) -> dict:
    """Parse JSON from a model response, tolerating markdown fences.

    Raises ProviderError with the raw text context when parsing fails.
    """
    if not isinstance(text, str):
        text = str(text)

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # Extract the first balanced JSON object/array if there is surrounding text.
    if not cleaned.startswith(("{", "[")):
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(1)

    # Repair common small-model output defects: trailing commas.
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"Provider returned invalid JSON: {exc}. "
            f"Response starts with: {text[:200]!r}"
        )

    if not isinstance(parsed, dict):
        raise ProviderError(
            "Provider returned JSON that is not an object. "
            f"Got: {type(parsed).__name__}"
        )

    return parsed

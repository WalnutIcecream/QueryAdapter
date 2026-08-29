"""Provider abstraction: decouple the pipeline from any single LLM vendor."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from queryadapter.errors import ProviderError


class Provider(ABC):
    """Minimal interface every language model backend implements.

    QueryAdapter only needs JSON generation for intent resolution and text
    generation for conversational answers. Providers that support JSON schema
    constraints should use them; the pipeline treats them as a best effort and
    never relies on a vendor for security.
    """

    name: str = "base"

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> dict:
        """Return a JSON object (dict) for the given prompt.

        Must raise :class:`ProviderError` on failure rather than returning a
        partial or arbitrary value.
        """

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> str:
        """Return free-form text for conversational answers."""

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ProviderError(message)

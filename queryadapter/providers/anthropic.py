"""Anthropic provider."""

from typing import Optional

from queryadapter.errors import ProviderError
from queryadapter.providers.base import Provider
from queryadapter.providers._json import extract_json


class AnthropicProvider(Provider):
    """Anthropic Messages API provider.

    Args:
        api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY``.
        model: Model name (default ``claude-3-5-haiku-latest``).
    """

    name = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-haiku-latest",
    ):
        import os

        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def _client(self):
        self._require(bool(self.api_key), "Anthropic API key is required")
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic package is required for AnthropicProvider. "
                "Install with: pip install queryadapter[anthropic]"
            ) from exc
        return anthropic.Anthropic(api_key=self.api_key)

    def generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> dict:
        client = self._client()
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return extract_json(text)

    def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> str:
        client = self._client()
        kwargs = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Anthropic request failed: {exc}") from exc

        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

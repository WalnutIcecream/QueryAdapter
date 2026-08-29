"""OpenAI provider (also covers OpenAI-compatible APIs)."""

from typing import Optional

from queryadapter.errors import ProviderError
from queryadapter.providers.base import Provider
from queryadapter.providers._json import extract_json


class OpenAIProvider(Provider):
    """OpenAI Chat Completions provider.

    Args:
        api_key: OpenAI API key. Falls back to ``OPENAI_API_KEY``.
        model: Model name (default ``gpt-4o-mini``).
        base_url: Optional override for OpenAI-compatible endpoints
            (e.g. self-hosted vLLM, Azure, or local proxies).
    """

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        import os

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.base_url = base_url

    def _client(self):
        self._require(bool(self.api_key), "OpenAI API key is required")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                "openai package is required for OpenAIProvider. "
                "Install with: pip install queryadapter[openai]"
            ) from exc
        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def _chat(self, prompt: str, system: Optional[str], json_mode: bool) -> str:
        client = self._client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover - vendor SDK error types vary
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        content = response.choices[0].message.content
        return content or ""

    def generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> dict:
        return extract_json(self._chat(prompt, system, json_mode=True))

    def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> str:
        return self._chat(prompt, system, json_mode=False)

"""Ollama provider for local models."""

from typing import Optional

from queryadapter.errors import ProviderError
from queryadapter.providers.base import Provider
from queryadapter.providers._json import extract_json


class OllamaProvider(Provider):
    """Ollama local model provider.

    Args:
        model: Model name (default ``llama3.2:3b``).
        host: Ollama server URL (default ``http://localhost:11434``).
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2:3b",
        host: Optional[str] = None,
    ):
        self.model = model
        self.host = host

    def _client(self):
        try:
            import ollama
        except ImportError as exc:
            raise ProviderError(
                "ollama package is required for OllamaProvider. "
                "Install with: pip install queryadapter[ollama]"
            ) from exc
        if self.host:
            return ollama.Client(host=self.host)
        return ollama

    def generate_json(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        json_schema: Optional[dict] = None,
    ) -> dict:
        client = self._client()
        try:
            response = client.generate(
                model=self.model,
                prompt=prompt,
                system=system,
                format="json",
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        text = response.get("response", "") if isinstance(response, dict) else str(response)
        return extract_json(text)

    def generate_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> str:
        client = self._client()
        try:
            response = client.generate(
                model=self.model,
                prompt=prompt,
                system=system,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Ollama request failed: {exc}") from exc

        return response.get("response", "") if isinstance(response, dict) else str(response)

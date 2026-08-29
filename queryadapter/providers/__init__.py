"""Provider registry and factory."""

from typing import Optional

from queryadapter.errors import ConfigurationError
from queryadapter.providers.base import Provider


def create_provider(
    name: str = "ollama",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> Provider:
    """Create a provider by name.

    Supported names: ``openai``, ``anthropic``, ``ollama``. Unknown names raise
    :class:`ConfigurationError`.
    """
    key = name.lower()

    if key in ("openai", "openai-compatible"):
        from queryadapter.providers.openai import OpenAIProvider

        return OpenAIProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            base_url=base_url,
        )

    if key == "anthropic":
        from queryadapter.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=api_key,
            model=model or "claude-3-5-haiku-latest",
        )

    if key == "ollama":
        from queryadapter.providers.ollama import OllamaProvider

        return OllamaProvider(model=model or "llama3.2:3b", host=base_url)

    raise ConfigurationError(
        f"Unknown provider {name!r}. Supported: openai, anthropic, ollama"
    )


__all__ = [
    "Provider",
    "create_provider",
]

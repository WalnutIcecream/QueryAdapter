"""Tests for the provider abstraction and JSON extraction."""

import pytest

from queryadapter.errors import ProviderError, ConfigurationError
from queryadapter.providers import create_provider
from queryadapter.providers._json import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_markdown_fence():
    text = "```json\n{\"a\": 1}\n```"
    assert extract_json(text) == {"a": 1}


def test_extract_json_surrounding_text():
    text = "Here is the plan: {\"a\": 1} thanks"
    assert extract_json(text) == {"a": 1}


def test_extract_json_trailing_comma_repair():
    assert extract_json('{"a": 1,}') == {"a": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(ProviderError):
        extract_json("not json")


def test_extract_json_non_object_raises():
    with pytest.raises(ProviderError):
        extract_json("[1, 2, 3]")


def test_create_provider_unknown_raises():
    with pytest.raises(ConfigurationError):
        create_provider("does-not-exist")


def test_create_ollama_provider():
    provider = create_provider("ollama", model="llama3.2:1b")
    assert provider.name == "ollama"
    assert provider.model == "llama3.2:1b"


def test_create_openai_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = create_provider("openai", api_key="test-key", model="gpt-test")
    assert provider.api_key == "test-key"


def test_create_anthropic_provider_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = create_provider("anthropic", api_key="test-key")
    assert provider.api_key == "test-key"

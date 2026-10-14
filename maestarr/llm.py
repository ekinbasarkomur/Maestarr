"""Model selection — builds a pydantic-ai model from the saved LLM settings.

The key is passed to the provider explicitly (it comes from the UI/database,
not from the provider's own env var), so changing it in Settings takes effect
on the next message without a restart.

Note: in pydantic-ai 2.x plain `openai:` means the Responses API; Ollama and
OpenAI-compatible servers need the Chat Completions model, built below.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic_ai.models import Model

from maestarr.config import LlmProvider, Settings, secret

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-5.4",
    "google": "gemini-3.1-pro-preview",
    "openrouter": "anthropic/claude-sonnet-5-5",
    "ollama": "qwen3:14b",
    "openai-compat": "",
}


class ModelNotConfigured(ValueError):
    pass


def split_model(settings: Settings) -> tuple[LlmProvider, str]:
    """Provider and model name, accepting a legacy "provider:model" value.

    >>> s = Settings(_env_file=None, MAESTARR_MODEL="openai:gpt-5.4")
    >>> split_model(s)
    ('openai', 'gpt-5.4')
    >>> split_model(Settings(_env_file=None, MAESTARR_LLM_PROVIDER="ollama", MAESTARR_MODEL="qwen3:14b"))
    ('ollama', 'qwen3:14b')
    """
    provider = settings.MAESTARR_LLM_PROVIDER
    name = settings.MAESTARR_MODEL.strip()
    head, sep, tail = name.partition(":")
    if sep and head in DEFAULT_MODELS and provider != "ollama":
        return head, tail  # type: ignore[return-value]
    return provider, name


def build_model_from(
    provider: str,
    name: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    http_client: Any = None,
) -> Model:
    if not name:
        raise ModelNotConfigured("no model name set")
    if provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        if not api_key:
            raise ModelNotConfigured("an Anthropic API key is required")
        return AnthropicModel(name, provider=AnthropicProvider(api_key=api_key, http_client=http_client))
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIResponsesModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if not api_key:
            raise ModelNotConfigured("an OpenAI API key is required")
        return OpenAIResponsesModel(name, provider=OpenAIProvider(api_key=api_key, http_client=http_client))
    if provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        if not api_key:
            raise ModelNotConfigured("a Google AI Studio API key is required")
        return GoogleModel(name, provider=GoogleProvider(api_key=api_key, http_client=http_client))
    if provider == "openrouter":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        if not api_key:
            raise ModelNotConfigured("an OpenRouter API key is required")
        return OpenAIChatModel(
            name, provider=OpenRouterProvider(api_key=api_key, app_title="Maestarr", http_client=http_client)
        )
    if provider in ("ollama", "openai-compat"):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        url = base_url or ("http://localhost:11434/v1" if provider == "ollama" else None)
        if not url:
            raise ModelNotConfigured("a base URL is required for an OpenAI-compatible server")
        if provider == "ollama" and not url.rstrip("/").endswith("/v1"):
            url = url.rstrip("/") + "/v1"
        return OpenAIChatModel(
            name, provider=OpenAIProvider(base_url=url, api_key=api_key or "not-needed", http_client=http_client)
        )
    raise ModelNotConfigured(f"unknown provider {provider!r}")


def build_model(settings: Settings) -> Model:
    provider, name = split_model(settings)
    return build_model_from(
        provider,
        name,
        api_key=secret(settings.MAESTARR_LLM_API_KEY),
        base_url=settings.MAESTARR_MODEL_BASE_URL,
    )


def model_label(settings: Settings) -> str:
    provider, name = split_model(settings)
    return f"{provider} · {name}"

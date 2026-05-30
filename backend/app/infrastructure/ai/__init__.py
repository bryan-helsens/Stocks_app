"""AI provider factory.

Selects an :class:`LLMProvider` implementation by name. The user's preferred
provider (and any API keys) come from their settings; the system default is
Ollama (local) for privacy. New providers plug in here without touching the
AI analysis service.
"""

from __future__ import annotations

from app.core.config import settings
from app.domain.ports.llm import LLMProvider
from app.domain.value_objects.enums import AIProvider
from app.infrastructure.ai.claude_provider import ClaudeProvider
from app.infrastructure.ai.ollama_provider import OllamaProvider
from app.infrastructure.ai.openai_provider import OpenAIProvider


def get_llm_provider(
    provider: AIProvider | str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMProvider:
    """Return an LLM provider instance for *provider* (defaults to settings)."""
    name = str(provider or settings.AI_PROVIDER).upper()
    if name == AIProvider.OPENAI:
        return OpenAIProvider(api_key=api_key, model=model)
    if name == AIProvider.CLAUDE:
        return ClaudeProvider(api_key=api_key, model=model)
    return OllamaProvider(model=model)

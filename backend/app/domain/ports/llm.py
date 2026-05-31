"""Port for Large Language Model providers (AI analyst, M12/M13).

The application builds a deterministic context (computed by the domain layer)
and asks an :class:`LLMProvider` to *interpret* it and return structured JSON.
The LLM never computes core financial figures (architecture principle: domain
calculates, LLM interprets). Providers: OpenAI, Claude, Ollama (local).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(slots=True)
class LLMResponse:
    """A model response plus provenance metadata for auditing."""

    content: str
    provider: str
    model: str
    raw: dict[str, Any]


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract chat-completion provider."""

    #: Provider identifier ("OPENAI" | "CLAUDE" | "OLLAMA").
    name: str
    model: str

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """Return a completion; when *json_mode* the content must be valid JSON."""
        ...

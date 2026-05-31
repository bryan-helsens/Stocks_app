"""Ollama (local) adapter — privacy-preserving default.

Talks to a locally running Ollama server, so portfolio data never leaves the
user's own infrastructure (FR12.3). Uses the /api/chat endpoint with
``format: json`` for structured output.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.domain.ports.llm import LLMMessage, LLMResponse


class OllamaProvider:
    name = "OLLAMA"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Ollama request failed (is it running at {self._base_url}?): {exc}"
            ) from exc

        content = data.get("message", {}).get("content", "")
        return LLMResponse(content=content, provider=self.name, model=self.model, raw=data)

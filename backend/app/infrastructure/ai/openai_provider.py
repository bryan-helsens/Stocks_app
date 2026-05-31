"""OpenAI chat-completions adapter (implements the LLMProvider port).

Uses httpx directly (no SDK dependency) so the surface stays small and testable.
Errors are surfaced as :class:`ExternalServiceError` for uniform handling.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.domain.ports.llm import LLMMessage, LLMResponse


class OpenAIProvider:
    name = "OPENAI"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self._base_url = "https://api.openai.com/v1"

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        if not self._api_key:
            raise ExternalServiceError("OpenAI API key is not configured.")

        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"OpenAI request failed: {exc}") from exc

        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, provider=self.name, model=self.model, raw=data)

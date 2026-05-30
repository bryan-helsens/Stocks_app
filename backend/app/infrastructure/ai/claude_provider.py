"""Anthropic Claude adapter (implements the LLMProvider port).

Uses the Messages API via httpx. Anthropic separates the system prompt from the
message list, so system messages are concatenated into the ``system`` field.
JSON output is requested via the prompt (Anthropic has no strict json_mode), and
the calling service validates/repairs the JSON.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.domain.ports.llm import LLMMessage, LLMResponse


class ClaudeProvider:
    name = "CLAUDE"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self.model = model or settings.CLAUDE_MODEL
        self._base_url = "https://api.anthropic.com/v1"

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        if not self._api_key:
            raise ExternalServiceError("Anthropic API key is not configured.")

        system_parts = [m.content for m in messages if m.role == "system"]
        chat = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        system_prompt = "\n\n".join(system_parts)
        if json_mode:
            system_prompt += "\n\nReturn ONLY valid JSON, with no surrounding prose."

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": chat,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self._base_url}/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Claude request failed: {exc}") from exc

        # Messages API returns a list of content blocks.
        content = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        return LLMResponse(content=content, provider=self.name, model=self.model, raw=data)

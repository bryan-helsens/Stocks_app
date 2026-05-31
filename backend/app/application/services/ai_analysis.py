"""AI analysis application service (M12/M13) — deliverable 11 core.

Design principle (architecture #5): the **domain layer computes** all financial
figures (allocations, ratios, risk, valuation); the **LLM only interprets** that
deterministic context and returns structured JSON. The LLM never produces the
numbers, which keeps results auditable and free of numeric hallucination.

Pipeline:
    build_context (deterministic) → LLM.complete(json) → validate (Pydantic)
        → on invalid JSON: one repair retry → else safe fallback
        → attach mandatory disclaimer → persist (audit) → return
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.core.logging import get_logger
from app.domain.ports.llm import LLMMessage, LLMProvider
from app.domain.value_objects.enums import Recommendation
from app.schemas.common import DISCLAIMER_NL

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "Je bent een educatieve beleggingsanalist. Je geeft GEEN financieel advies. "
    "Je interpreteert uitsluitend de aangeleverde, vooraf berekende cijfers en "
    "verwoordt observaties, risico's en kansen in het Nederlands. Je verzint geen "
    "cijfers en herberekent niets. Antwoord ALTIJD met geldige JSON volgens het "
    "opgegeven schema. Gebruik nooit stellige garanties; formuleer informatief."
)

# JSON schema (as text) the model must follow.
_PORTFOLIO_SCHEMA = (
    '{"summary": str, "risk_score": number(0-100), "concentration_note": str, '
    '"strengths": [str], "weaknesses": [str], "opportunities": [str], "threats": [str]}'
)
_POSITION_SCHEMA = (
    '{"recommendation": one of ["STRONG_BUY","BUY","HOLD","REDUCE","SELL"], '
    '"confidence": number(0-1), "risk_score": number(0-100), "summary": str, '
    '"strengths": [str], "weaknesses": [str], "opportunities": [str], "threats": [str]}'
)


# --------------------------------------------------------------------------- #
# Validated output models
# --------------------------------------------------------------------------- #
class PortfolioAnalysis(BaseModel):
    summary: str = ""
    risk_score: float = 50.0
    concentration_note: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_NL


class PositionAnalysis(BaseModel):
    recommendation: Recommendation = Recommendation.HOLD
    confidence: float = 0.5
    risk_score: float = 50.0
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER_NL


@dataclass(slots=True)
class AnalysisResult:
    """Validated analysis plus provenance for the audit trail."""

    data: dict
    provider: str
    model: str
    context: dict
    raw: dict = field(default_factory=dict)


class AIAnalysisService:
    def __init__(self, provider: LLMProvider) -> None:
        self._llm = provider

    # ----- portfolio-level ----------------------------------------------
    async def analyze_portfolio(self, context: dict) -> AnalysisResult:
        """Analyse a whole-portfolio context bundle."""
        prompt = (
            "Analyseer de volgende portefeuille-context (alle cijfers zijn reeds "
            f"berekend). Antwoord met JSON in dit schema: {_PORTFOLIO_SCHEMA}\n\n"
            f"CONTEXT:\n{json.dumps(context, ensure_ascii=False, default=_json_default)}"
        )
        data = await self._run(prompt, PortfolioAnalysis, context)
        return data

    # ----- position-level (Buy/Hold/Sell) -------------------------------
    async def analyze_position(self, context: dict) -> AnalysisResult:
        """Produce a Buy/Hold/Sell signal for a single position."""
        prompt = (
            "Geef een educatief Koop/Houd/Verkoop-signaal voor de positie op basis "
            "van de reeds berekende cijfers. Geen advies, enkel informatieve "
            f"signalen. Antwoord met JSON in dit schema: {_POSITION_SCHEMA}\n\n"
            f"CONTEXT:\n{json.dumps(context, ensure_ascii=False, default=_json_default)}"
        )
        return await self._run(prompt, PositionAnalysis, context)

    # ----- shared LLM runner --------------------------------------------
    async def _run(
        self, prompt: str, model_cls: type[BaseModel], context: dict
    ) -> AnalysisResult:
        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        response = await self._llm.complete(messages, json_mode=True)
        parsed = self._parse(response.content, model_cls)

        if parsed is None:
            # One repair attempt: ask the model to fix its JSON.
            repair = [
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=(
                        "Je vorige antwoord was geen geldige JSON. Geef UITSLUITEND "
                        f"geldige JSON volgens het schema. Vorige output:\n{response.content}"
                    ),
                ),
            ]
            response = await self._llm.complete(repair, json_mode=True)
            parsed = self._parse(response.content, model_cls)

        if parsed is None:
            # Safe fallback — never fail the request because the model misbehaved.
            logger.warning("ai_invalid_json", provider=self._llm.name)
            parsed = model_cls()  # defaults, with disclaimer

        # Ensure the disclaimer is always present (BR9).
        payload = parsed.model_dump()
        payload["disclaimer"] = DISCLAIMER_NL
        return AnalysisResult(
            data=payload,
            provider=self._llm.name,
            model=self._llm.model,
            context=context,
            raw=response.raw,
        )

    @staticmethod
    def _parse(content: str, model_cls: type[BaseModel]) -> BaseModel | None:
        text = _extract_json(content)
        if text is None:
            return None
        try:
            return model_cls.model_validate_json(text)
        except (PydanticValidationError, ValueError):
            return None


def _extract_json(content: str) -> str | None:
    """Extract the first JSON object from *content* (handles code fences)."""
    if not content:
        return None
    stripped = content.strip()
    if stripped.startswith("```"):
        # Remove ```json ... ``` fences.
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return stripped[start : end + 1]


def _json_default(obj: Any) -> str:
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)

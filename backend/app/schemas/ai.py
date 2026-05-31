"""AI analysis schemas (M12/M13)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.domain.value_objects.enums import AIProvider


class PortfolioAnalysisRequest(BaseModel):
    portfolio_id: UUID
    provider: AIProvider | None = None  # defaults to user/system setting


class PositionAnalysisRequest(BaseModel):
    portfolio_id: UUID
    asset_id: UUID
    provider: AIProvider | None = None


class PortfolioAnalysisResponse(BaseModel):
    provider: str
    model: str
    summary: str
    risk_score: float
    concentration_note: str
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]
    disclaimer: str


class PositionAnalysisResponse(BaseModel):
    provider: str
    model: str
    recommendation: str
    confidence: float
    risk_score: float
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    opportunities: list[str]
    threats: list[str]
    disclaimer: str

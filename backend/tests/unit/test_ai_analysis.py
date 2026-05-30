"""Unit tests for the AI analysis service using a fake LLM provider (no network)."""

from __future__ import annotations

import pytest

from app.application.services.ai_analysis import AIAnalysisService
from app.domain.ports.llm import LLMMessage, LLMResponse


class FakeLLM:
    name = "OLLAMA"
    model = "test-model"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        content = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return LLMResponse(content=content, provider=self.name, model=self.model, raw={"ok": True})


@pytest.mark.asyncio
async def test_portfolio_analysis_valid_json():
    valid = (
        '{"summary":"Sterk gespreid","risk_score":42,"concentration_note":"ok",'
        '"strengths":["cashflow"],"weaknesses":[],"opportunities":["EU"],"threats":["rente"]}'
    )
    svc = AIAnalysisService(FakeLLM([valid]))
    result = await svc.analyze_portfolio({"totals": {}})
    assert result.data["summary"] == "Sterk gespreid"
    assert result.data["risk_score"] == 42
    assert result.data["disclaimer"]  # always present


@pytest.mark.asyncio
async def test_position_analysis_repairs_then_succeeds():
    bad = "not json at all"
    good = (
        '{"recommendation":"HOLD","confidence":0.7,"risk_score":55,"summary":"stabiel",'
        '"strengths":[],"weaknesses":[],"opportunities":[],"threats":[]}'
    )
    llm = FakeLLM([bad, good])
    svc = AIAnalysisService(llm)
    result = await svc.analyze_position({"asset": {}})
    assert llm.calls == 2  # one repair retry
    assert result.data["recommendation"] == "HOLD"
    assert result.data["confidence"] == 0.7


@pytest.mark.asyncio
async def test_analysis_falls_back_on_persistent_garbage():
    llm = FakeLLM(["garbage", "still garbage"])
    svc = AIAnalysisService(llm)
    result = await svc.analyze_portfolio({})
    # Safe defaults, request never fails.
    assert "disclaimer" in result.data
    assert result.data["risk_score"] == 50.0


@pytest.mark.asyncio
async def test_json_inside_code_fence_is_parsed():
    fenced = '```json\n{"summary":"ok","risk_score":10,"concentration_note":"",' \
             '"strengths":[],"weaknesses":[],"opportunities":[],"threats":[]}\n```'
    svc = AIAnalysisService(FakeLLM([fenced]))
    result = await svc.analyze_portfolio({})
    assert result.data["summary"] == "ok"
    assert result.data["risk_score"] == 10

"""FIRE & scenario planner endpoints (M10/M11)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.application.services.fire_service import FireService
from app.schemas.fire import (
    FirePlanRequest,
    FirePlanResponse,
    FireTargetsResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    ScenarioRequest,
    ScenarioResponse,
)

router = APIRouter(prefix="/fire", tags=["fire"])
_service = FireService()


@router.post("/plan", response_model=FirePlanResponse)
async def compute_plan(body: FirePlanRequest, _: CurrentUser) -> FirePlanResponse:
    result = _service.compute_plan(
        annual_expenses=body.annual_expenses,
        swr=body.swr,
        current_value=body.current_value,
        monthly_contribution=body.monthly_contribution,
        expected_return=body.expected_return,
    )
    t = result.targets
    return FirePlanResponse(
        targets=FireTargetsResponse(
            full_number=t.full_number, lean=t.lean, coast=t.coast,
            barista=t.barista, fat=t.fat,
        ),
        fi_date=result.projection.fi_date,
        years_to_fi=result.projection.years_to_fi,
        projection=result.projection.yearly,
        inputs=result.inputs,
    )


@router.post("/scenario", response_model=ScenarioResponse)
async def run_scenario(body: ScenarioRequest, _: CurrentUser) -> ScenarioResponse:
    r = _service.run_scenario(
        initial_value=body.initial_value,
        monthly_contribution=body.monthly_contribution,
        annual_return=body.annual_return,
        years=body.years,
        name=body.name,
        crash_pct=body.crash_pct,
        crash_year=body.crash_year,
        inflation=body.inflation,
        extra_monthly=body.extra_monthly,
        dividend_change_pct=body.dividend_change_pct,
        annual_dividend=body.annual_dividend,
    )
    return ScenarioResponse(
        name=r.name, final_value=r.final_value, yearly=r.yearly, params=r.params,
    )


@router.post("/monte-carlo", response_model=MonteCarloResponse)
async def monte_carlo(body: MonteCarloRequest, _: CurrentUser) -> MonteCarloResponse:
    band = _service.monte_carlo(
        initial_value=body.initial_value,
        monthly_contribution=body.monthly_contribution,
        mean_return=body.mean_return,
        volatility=body.volatility,
        years=body.years,
        runs=body.runs,
    )
    return MonteCarloResponse(p10=band.p10, p50=band.p50, p90=band.p90, runs=band.runs)

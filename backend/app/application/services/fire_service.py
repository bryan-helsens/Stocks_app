"""FIRE & scenario application service (M10/M11).

Thin orchestration over the pure domain services (:mod:`app.domain.services.fire`
and :mod:`app.domain.services.scenarios`). Persists plans/scenarios and shapes
projections for the API. All outputs are estimates — never guarantees (BR9/BR10).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.services import fire, scenarios
from app.domain.services.fire import FireProjection, FireTargets


@dataclass(slots=True)
class FirePlanResult:
    targets: FireTargets
    projection: FireProjection
    inputs: dict


class FireService:
    """Computes FIRE targets, the FI projection and scenario simulations."""

    def compute_plan(
        self,
        *,
        annual_expenses: Decimal,
        swr: Decimal,
        current_value: Decimal,
        monthly_contribution: Decimal,
        expected_return: Decimal,
        today: date | None = None,
    ) -> FirePlanResult:
        today = today or date.today()
        targets = fire.fire_targets(
            annual_expenses=annual_expenses,
            swr=swr,
            current_value=current_value,
            expected_return=expected_return,
        )
        projection = fire.project_to_fi(
            current_value=current_value,
            monthly_contribution=monthly_contribution,
            expected_return=expected_return,
            target_value=targets.full_number,
            today=today,
        )
        return FirePlanResult(
            targets=targets,
            projection=projection,
            inputs={
                "annual_expenses": str(annual_expenses),
                "swr": str(swr),
                "current_value": str(current_value),
                "monthly_contribution": str(monthly_contribution),
                "expected_return": str(expected_return),
            },
        )

    def run_scenario(
        self,
        *,
        initial_value: Decimal,
        monthly_contribution: Decimal,
        annual_return: Decimal,
        years: int,
        name: str,
        crash_pct: Decimal | None = None,
        crash_year: int | None = None,
        inflation: Decimal | None = None,
        extra_monthly: Decimal | None = None,
        dividend_change_pct: Decimal | None = None,
        annual_dividend: Decimal | None = None,
    ) -> scenarios.ScenarioResult:
        return scenarios.simulate(
            initial_value=initial_value,
            monthly_contribution=monthly_contribution,
            annual_return=annual_return,
            years=years,
            name=name,
            one_off_crash_pct=crash_pct,
            crash_year=crash_year,
            inflation=inflation,
            extra_monthly=extra_monthly,
            dividend_change_pct=dividend_change_pct,
            annual_dividend=annual_dividend,
        )

    def monte_carlo(
        self,
        *,
        initial_value: Decimal,
        monthly_contribution: Decimal,
        mean_return: Decimal,
        volatility: Decimal,
        years: int,
        runs: int = 1000,
    ) -> scenarios.MonteCarloBand:
        return scenarios.monte_carlo(
            initial_value=initial_value,
            monthly_contribution=monthly_contribution,
            mean_annual_return=mean_return,
            annual_volatility=volatility,
            years=years,
            runs=runs,
        )

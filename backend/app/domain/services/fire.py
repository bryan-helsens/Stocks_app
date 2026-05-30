"""FIRE (Financial Independence / Retire Early) calculations.

Implements Lean / Coast / Barista / Fat FIRE targets, a projected financial-
independence date and a portfolio-value projection (M10). Everything here is an
**estimate** based on user assumptions — never a guarantee (BR9/BR10). The UI
must always render these with the educational disclaimer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.value_objects.money import to_decimal

# Multipliers applied to the base "full FIRE" number (1 / SWR) to derive
# the lifestyle variants. These are common community conventions, not advice.
_LEAN_FACTOR = Decimal("0.7")   # leaner lifestyle than baseline
_FAT_FACTOR = Decimal("2.0")    # ~2x the baseline annual spend
_BARISTA_FACTOR = Decimal("0.5")  # half covered by portfolio, half by part-time work


@dataclass(slots=True)
class FireTargets:
    """Target portfolio values for each FIRE flavour (base currency)."""

    full_number: Decimal
    lean: Decimal
    coast: Decimal
    barista: Decimal
    fat: Decimal
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class FireProjection:
    """Year-by-year projection of portfolio value and passive income."""

    fi_date: date | None
    years_to_fi: Decimal | None
    yearly: list[dict] = field(default_factory=list)


def fire_targets(
    annual_expenses: Decimal,
    swr: Decimal,
    current_value: Decimal,
    expected_return: Decimal,
    years_to_traditional_retirement: int = 30,
) -> FireTargets:
    """Compute FIRE target numbers.

    Args:
        annual_expenses: expected yearly spending in retirement.
        swr: safe withdrawal rate (e.g. 0.04 for the "4% rule").
        current_value: current invested portfolio value (for Coast).
        expected_return: real expected annual return (for Coast discounting).
        years_to_traditional_retirement: horizon used for the Coast number.

    Returns:
        :class:`FireTargets`. Coast FIRE is the amount that, left to compound at
        *expected_return* for the horizon, reaches the full number without
        further contributions.
    """
    expenses = to_decimal(annual_expenses)
    swr_d = to_decimal(swr)
    if swr_d <= 0:
        raise ValueError("Safe withdrawal rate must be positive")

    full_number = expenses / swr_d
    lean = (expenses * _LEAN_FACTOR) / swr_d
    fat = (expenses * _FAT_FACTOR) / swr_d
    barista = full_number * _BARISTA_FACTOR

    r = to_decimal(expected_return)
    horizon = max(0, years_to_traditional_retirement)
    growth = (Decimal(1) + r) ** horizon if r > -1 else Decimal(1)
    coast = full_number / growth if growth > 0 else full_number

    return FireTargets(
        full_number=full_number,
        lean=lean,
        coast=coast,
        barista=barista,
        fat=fat,
        notes={
            "swr": str(swr_d),
            "full_number_formula": "annual_expenses / swr",
            "coast_horizon_years": str(horizon),
        },
    )


def project_to_fi(
    current_value: Decimal,
    monthly_contribution: Decimal,
    expected_return: Decimal,
    target_value: Decimal,
    today: date,
    max_years: int = 60,
) -> FireProjection:
    """Project portfolio growth until *target_value* is reached.

    Uses monthly compounding of *expected_return* plus monthly contributions.
    Returns the estimated FI date and a yearly trace. If the target is already
    met, ``years_to_fi`` is 0 and ``fi_date`` is *today*.
    """
    value = to_decimal(current_value)
    target = to_decimal(target_value)
    contrib = to_decimal(monthly_contribution)
    monthly_rate = to_decimal(expected_return) / Decimal(12)

    yearly: list[dict] = [{"year": 0, "value": value}]

    if value >= target:
        return FireProjection(fi_date=today, years_to_fi=Decimal(0), yearly=yearly)

    months = 0
    fi_date: date | None = None
    years_to_fi: Decimal | None = None
    for month in range(1, max_years * 12 + 1):
        value = value * (Decimal(1) + monthly_rate) + contrib
        months = month
        if month % 12 == 0:
            yearly.append({"year": month // 12, "value": value})
        if value >= target:
            years_to_fi = to_decimal(months) / Decimal(12)
            fi_date = _add_months(today, months)
            if month % 12 != 0:
                yearly.append({"year": round(month / 12, 2), "value": value})
            break

    return FireProjection(fi_date=fi_date, years_to_fi=years_to_fi, yearly=yearly)


def _add_months(start: date, months: int) -> date:
    """Return *start* shifted forward by *months* (clamping the day)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp day to the last valid day of the target month.
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days

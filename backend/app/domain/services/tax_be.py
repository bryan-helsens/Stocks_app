"""Belgian tax calculations — INFORMATIONAL / EDUCATIONAL ONLY (M17).

⚠️  This module does **not** provide tax or legal advice. It produces indicative
overviews to simplify record-keeping. Rates, caps and exemptions change and may
not fit every personal situation — users must verify with the FOD Financiën /
their accountant. Rates are parameterised so they can be updated without code
changes elsewhere.

Implements (informational):
  * Roerende voorheffing (RV) — Belgian withholding on dividend income (30%).
  * Foreign withholding tax (bronbelasting) handling for foreign dividends.
  * Beurstaks (TOB / taxe sur les opérations de bourse) per instrument type,
    with statutory per-transaction caps.
  * Aggregation of dividend income, taxes and transaction costs per year.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.value_objects.enums import AssetClass
from app.domain.value_objects.money import to_decimal

# --------------------------------------------------------------------------- #
# Statutory parameters (review annually — informational defaults).
# --------------------------------------------------------------------------- #
BELGIAN_RV_RATE = Decimal("0.30")  # roerende voorheffing on dividends

# TOB rates by instrument category and statutory per-transaction caps (EUR).
# Source convention (subject to change): individual shares 0.35% (cap €1600),
# distributing/registered funds 0.12% (cap €1300), accumulating funds 1.32%
# (cap €4000), bonds 0.12% (cap €1300).
TOB_RATES: dict[str, Decimal] = {
    "stock": Decimal("0.0035"),
    "fund_distributing": Decimal("0.0012"),
    "fund_accumulating": Decimal("0.0132"),
    "bond": Decimal("0.0012"),
}
TOB_CAPS: dict[str, Decimal] = {
    "stock": Decimal("1600"),
    "fund_distributing": Decimal("1300"),
    "fund_accumulating": Decimal("4000"),
    "bond": Decimal("1300"),
}

# Annual dividend exemption that can typically be reclaimed via the tax return.
# Indexed yearly; supplied as a parameter with a conservative default.
DEFAULT_DIVIDEND_EXEMPTION = Decimal("833")


@dataclass(slots=True)
class TobResult:
    rate: Decimal
    raw_tax: Decimal
    capped_tax: Decimal
    category: str


def compute_tob(
    transaction_value: Decimal,
    asset_class: AssetClass,
    is_accumulating: bool = False,
) -> TobResult:
    """Compute the Belgian transaction tax (TOB) for a single trade.

    Args:
        transaction_value: the gross value of the trade (price × quantity).
        asset_class: used to pick the applicable rate category.
        is_accumulating: distinguishes accumulating vs distributing funds (ETFs).

    Returns:
        A :class:`TobResult` with the raw and cap-limited tax. Cash and crypto
        are treated as out of TOB scope (rate 0).
    """
    value = to_decimal(transaction_value)
    category = _tob_category(asset_class, is_accumulating)
    rate = TOB_RATES.get(category, Decimal(0))
    raw = value * rate
    cap = TOB_CAPS.get(category)
    capped = min(raw, cap) if cap is not None else raw
    return TobResult(rate=rate, raw_tax=raw, capped_tax=capped, category=category)


def _tob_category(asset_class: AssetClass, is_accumulating: bool) -> str:
    if asset_class in (AssetClass.STOCK, AssetClass.REIT):
        return "stock"
    if asset_class == AssetClass.BOND:
        return "bond"
    if asset_class == AssetClass.ETF:
        return "fund_accumulating" if is_accumulating else "fund_distributing"
    return "none"  # CASH, CRYPTO — out of scope here


@dataclass(slots=True)
class DividendTaxLine:
    """Per-dividend breakdown of foreign and Belgian taxation (informational)."""

    asset: str
    source_country: str | None
    gross: Decimal
    foreign_withholding: Decimal
    belgian_rv: Decimal
    net: Decimal
    is_foreign: bool


def compute_dividend_tax(
    gross: Decimal,
    source_country: str | None,
    foreign_withholding_rate: Decimal,
    residence_country: str = "BE",
    asset_label: str = "",
    rv_rate: Decimal = BELGIAN_RV_RATE,
) -> DividendTaxLine:
    """Compute taxes on a single dividend (informational).

    Belgian RV is levied on the dividend **after** any foreign withholding tax.
    For Belgian-source dividends there is no foreign withholding.

    Args:
        gross: gross dividend amount in base currency.
        foreign_withholding_rate: rate withheld at source (0 for BE dividends).
    """
    g = to_decimal(gross)
    is_foreign = (source_country or "").upper() not in ("", residence_country.upper())
    fw_rate = to_decimal(foreign_withholding_rate) if is_foreign else Decimal(0)
    foreign_wht = g * fw_rate
    after_foreign = g - foreign_wht
    belgian_rv = after_foreign * to_decimal(rv_rate)
    net = after_foreign - belgian_rv
    return DividendTaxLine(
        asset=asset_label,
        source_country=source_country,
        gross=g,
        foreign_withholding=foreign_wht,
        belgian_rv=belgian_rv,
        net=net,
        is_foreign=is_foreign,
    )


@dataclass(slots=True)
class TaxSummary:
    """Annual Belgian tax overview (informational)."""

    year: int
    foreign_dividends_gross: Decimal = Decimal(0)
    belgian_dividends_gross: Decimal = Decimal(0)
    withholding_tax_foreign: Decimal = Decimal(0)
    belgian_rv: Decimal = Decimal(0)
    tob_total: Decimal = Decimal(0)
    fees_total: Decimal = Decimal(0)
    net_dividend_income: Decimal = Decimal(0)
    reclaimable_exemption: Decimal = Decimal(0)
    lines: list[DividendTaxLine] = field(default_factory=list)
    disclaimer: str = (
        "Dit overzicht is uitsluitend informatief en educatief en vormt geen "
        "fiscaal of juridisch advies. Verifieer met de FOD Financiën of je "
        "boekhouder."
    )


def build_tax_summary(
    year: int,
    dividend_lines: list[DividendTaxLine],
    tob_total: Decimal,
    fees_total: Decimal,
    dividend_exemption: Decimal = DEFAULT_DIVIDEND_EXEMPTION,
) -> TaxSummary:
    """Aggregate dividend tax lines and costs into an annual summary (FR17.2)."""
    summary = TaxSummary(year=year, tob_total=to_decimal(tob_total),
                         fees_total=to_decimal(fees_total), lines=dividend_lines)
    for line in dividend_lines:
        if line.is_foreign:
            summary.foreign_dividends_gross += line.gross
        else:
            summary.belgian_dividends_gross += line.gross
        summary.withholding_tax_foreign += line.foreign_withholding
        summary.belgian_rv += line.belgian_rv
        summary.net_dividend_income += line.net

    total_gross = summary.foreign_dividends_gross + summary.belgian_dividends_gross
    summary.reclaimable_exemption = min(to_decimal(dividend_exemption), total_gross)
    return summary

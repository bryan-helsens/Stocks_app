"""Unit tests for the BUX parser against a representative synthetic sample.

The sample (docs/samples/bux_sample.csv) mirrors the real BUX export format:
double-entry trades, foreign-currency FX, dividends with gross/net/tax columns,
fees, Belgian Tob tax, interest income and an asset transfer.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.infrastructure.brokers import select_parser
from app.infrastructure.brokers.bux import BuxParser
from app.domain.value_objects.enums import TransactionType

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "bux_sample.csv"


@pytest.fixture
def content() -> bytes:
    return SAMPLE.read_bytes()


def test_bux_is_autoselected(content: bytes):
    parser = select_parser("bux_export.csv", content[:4096])
    assert parser is not None
    assert parser.parser_key == "bux"


def test_asset_legs_are_skipped(content: bytes):
    result = BuxParser().parse(content)
    # 10 data rows; 2 are ASSET_TRADE_* legs of the buy/sell -> dropped.
    assert len(result.drafts) == 8
    assert result.warnings == []


def test_buy_uses_asset_currency_and_fx_to_eur(content: bytes):
    result = BuxParser().parse(content)
    buy = next(d for d in result.drafts if d.type == TransactionType.BUY)
    assert buy.isin == "US0378331005"
    assert buy.name == "Apple"
    assert buy.quantity == Decimal("0.161834")
    assert buy.price == Decimal("174.0")
    assert buy.currency == "USD"
    # fx to EUR = 1 / 1.12637
    assert buy.fx_rate == Decimal(1) / Decimal("1.12637")


def test_dividend_gross_and_tax_in_dividend_currency(content: bytes):
    result = BuxParser().parse(content)
    div = next(d for d in result.drafts if d.type == TransactionType.DIVIDEND)
    assert div.gross_amount == Decimal("0.04")
    assert div.tax == Decimal("0.01")
    assert div.currency == "USD"


def test_tob_is_tax(content: bytes):
    result = BuxParser().parse(content)
    tax = next(d for d in result.drafts if d.type == TransactionType.TAX)
    assert tax.tax == Decimal("0.34")
    assert tax.currency == "EUR"


def test_fee_row(content: bytes):
    result = BuxParser().parse(content)
    fee = next(d for d in result.drafts if d.type == TransactionType.FEE)
    assert fee.fee == Decimal("1.0")


def test_interest_mapped_to_deposit(content: bytes):
    result = BuxParser().parse(content)
    deposits = [d for d in result.drafts if d.type == TransactionType.DEPOSIT]
    # Sepa Deposit + Interest Payment both become DEPOSIT cash inflows.
    assert len(deposits) == 2


def test_asset_transfer_flagged_for_review(content: bytes):
    result = BuxParser().parse(content)
    review = [d for d in result.drafts if d.type is None]
    assert len(review) == 1
    assert "Portfolio Transfer" in (review[0].note or "")

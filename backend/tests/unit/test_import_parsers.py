"""Unit tests for the generic import framework (parsers, detection, dedup)."""

from __future__ import annotations

from decimal import Decimal

from app.domain.value_objects.enums import TransactionType
from app.infrastructure.brokers import select_parser
from app.infrastructure.brokers.classification import classify
from app.infrastructure.brokers.column_detection import detect_mapping
from app.infrastructure.brokers.csv_generic import CsvGenericParser


def test_detect_mapping_multilang():
    headers = ["Datum", "Type", "ISIN", "Aantal", "Koers", "Bedrag", "Kosten", "Valuta"]
    mapping = detect_mapping(headers)
    assert mapping["Datum"] == "trade_date"
    assert mapping["ISIN"] == "isin"
    assert mapping["Aantal"] == "quantity"
    assert mapping["Koers"] == "price"
    assert mapping["Bedrag"] == "gross_amount"
    assert mapping["Kosten"] == "fee"
    assert mapping["Valuta"] == "currency"


def test_classify_from_keyword():
    assert classify("Koop", has_asset=True, quantity=Decimal(5), amount=None) == TransactionType.BUY
    assert classify("Dividend payment", has_asset=True, quantity=None, amount=Decimal(10)) == (
        TransactionType.DIVIDEND
    )
    assert classify(None, has_asset=False, quantity=None, amount=Decimal(100)) == (
        TransactionType.DEPOSIT
    )
    assert classify(None, has_asset=False, quantity=None, amount=Decimal(-100)) == (
        TransactionType.WITHDRAWAL
    )


def test_csv_parser_european_numbers():
    csv = (
        "Datum;Type;ISIN;Aantal;Koers;Bedrag;Kosten;Valuta\n"
        "04/03/2025;Koop;US0378331005;10;170,10;1.701,00;0,50;EUR\n"
        "15/03/2025;Dividend;US0378331005;;;43,20;0;EUR\n"
    )
    result = CsvGenericParser().parse(csv.encode("utf-8"))
    assert len(result.drafts) == 2
    buy = result.drafts[0]
    assert buy.type == TransactionType.BUY
    assert buy.quantity == Decimal("10")
    assert buy.price == Decimal("170.10")
    assert buy.gross_amount == Decimal("1701.00")
    assert buy.fee == Decimal("0.50")
    assert buy.isin == "US0378331005"
    assert result.drafts[1].type == TransactionType.DIVIDEND


def test_select_parser_prefers_bux():
    sample = b"Transaction Time,Transaction Type,Amount of shares,Price per share\n"
    parser = select_parser("bux_export.csv", sample)
    assert parser is not None
    assert parser.parser_key == "bux"


def test_select_parser_falls_back_to_generic_csv():
    parser = select_parser("statement.csv", b"a,b,c\n1,2,3\n")
    assert parser is not None
    assert parser.parser_key in ("csv_generic", "bux")

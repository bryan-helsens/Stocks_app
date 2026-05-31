"""Generic delimited (CSV/TSV) statement parser.

Auto-detects the delimiter and column mapping, then normalises each row into a
:class:`TransactionDraft`. Robust to European number formats (``1.234,56``) and
several date layouts. A user-supplied ``column_mapping`` overrides detection.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.domain.ports.broker_parser import ParseResult, TransactionDraft
from app.infrastructure.brokers.classification import classify
from app.infrastructure.brokers.column_detection import detect_mapping

_DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M",
)


class CsvGenericParser:
    parser_key = "csv_generic"

    def can_parse(self, filename: str, sample: bytes) -> bool:
        return filename.lower().endswith((".csv", ".tsv", ".txt"))

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        text = _decode(content)
        delimiter = _sniff_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = reader.fieldnames or []
        mapping = column_mapping or detect_mapping(headers)

        drafts: list[TransactionDraft] = []
        warnings: list[str] = []
        for i, row in enumerate(reader, start=2):
            try:
                draft = self._row_to_draft(row, mapping)
                if draft is not None:
                    drafts.append(draft)
            except Exception as exc:  # noqa: BLE001 - keep importing other rows
                warnings.append(f"Row {i}: {exc}")

        return ParseResult(
            drafts=drafts,
            detected_columns=headers,
            column_mapping=mapping,
            warnings=warnings,
        )

    def _row_to_draft(self, row: dict, mapping: dict[str, str]) -> TransactionDraft | None:
        fields: dict[str, str] = {}
        for original, field in mapping.items():
            value = row.get(original)
            if value is not None and str(value).strip() != "":
                fields[field] = str(value).strip()

        if not fields:
            return None

        trade_date = _parse_date(fields.get("trade_date"))
        if trade_date is None:
            raise ValueError("missing or unparseable trade date")

        quantity = _parse_decimal(fields.get("quantity"))
        price = _parse_decimal(fields.get("price"))
        gross = _parse_decimal(fields.get("gross_amount"))
        fee = _parse_decimal(fields.get("fee")) or Decimal(0)
        tax = _parse_decimal(fields.get("tax")) or Decimal(0)
        ticker = fields.get("ticker")
        isin = fields.get("isin")

        tx_type = classify(
            fields.get("type"),
            has_asset=bool(ticker or isin),
            quantity=quantity,
            amount=gross,
        )

        return TransactionDraft(
            trade_date=trade_date,
            type=tx_type,
            ticker=ticker,
            isin=isin,
            name=fields.get("name"),
            quantity=abs(quantity) if quantity is not None else None,
            price=price,
            gross_amount=abs(gross) if gross is not None else None,
            fee=fee,
            tax=tax,
            currency=(fields.get("currency") or "EUR").upper()[:3],
            fx_rate=_parse_decimal(fields.get("fx_rate")),
            external_id=fields.get("external_id"),
            raw=dict(row),
        )


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # Fall back to the most frequent candidate in the header line.
        header = text.splitlines()[0] if text.splitlines() else ""
        return max(",;\t|", key=header.count)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _parse_decimal(value: str | None) -> Decimal | None:
    """Parse a number tolerating European thousands/decimal separators."""
    if value is None:
        return None
    v = value.strip().replace(" ", "").replace(" ", "")
    if v == "":
        return None
    # Strip currency symbols.
    v = v.replace("€", "").replace("$", "").replace("£", "")
    # If both separators present, the last one is the decimal separator.
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    elif "," in v:
        # Single comma: treat as decimal separator (European).
        v = v.replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None

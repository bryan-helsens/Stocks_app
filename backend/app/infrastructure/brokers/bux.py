"""BUX statement parser — tuned to the real BUX CSV export.

The BUX export uses **double-entry accounting**: every trade appears twice, once
as a cash leg (``CASH_DEBIT``/``CASH_CREDIT``) and once as an asset leg
(``ASSET_TRADE_BUY``/``ASSET_TRADE_SELL``). To avoid double counting we keep the
**cash leg** (it carries the EUR cash impact, the asset quantity/price and the
FX rate) and drop the asset leg.

Columns (header):
    Transaction Time (CET), Transaction Category, Transaction Type, Transfer Type,
    Transaction Amount, Transaction Currency, Cash Balance Amount, Asset Id,
    Asset Name, Asset Quantity, Asset Price, Asset Currency, Currency Pair,
    Exchange Rate, Profit And Loss Amount, Profit And Loss Currency,
    Dividend Currency, Dividend Gross Amount, Dividend Net Amount,
    Dividend Tax Amount, Transaction Description

FX convention: ``Currency Pair`` is ``EURXXX`` with ``Exchange Rate`` = XXX per
EUR. The asset price is in the asset currency (XXX), so the rate to the EUR base
currency is ``1 / Exchange Rate``.

Note on income types: BUX has interest / promotional / lending revenue rows. The
domain has no dedicated INCOME type, so these cash inflows are mapped to
``DEPOSIT`` to keep the cash balance correct; this is a pragmatic, documented
choice (the description is preserved in ``raw``).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.domain.ports.broker_parser import ParseResult, TransactionDraft
from app.domain.value_objects.enums import TransactionType

# Transfer types that are the *asset* leg of a trade — skipped (cash leg kept).
_SKIP_TRANSFER_TYPES = {"ASSET_TRADE_BUY", "ASSET_TRADE_SELL"}

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
_ORDER_ID_RE = re.compile(r"Order(?:\sPartial)?\sId:\s*([0-9a-f-]+)", re.IGNORECASE)

_BUX_HEADER_TOKENS = ("transaction category", "transfer type", "asset id", "dividend gross amount")


class BuxParser:
    parser_key = "bux"

    def can_parse(self, filename: str, sample: bytes) -> bool:
        head = sample[:4096].decode("utf-8", errors="ignore").lower()
        if not (filename.lower().endswith(".csv") or "%pdf" not in head):
            return False
        # Strong signal: the BUX-specific header columns.
        return sum(token in head for token in _BUX_HEADER_TOKENS) >= 2 or "bux" in filename.lower()

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        text = _decode(content)
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []

        drafts: list[TransactionDraft] = []
        warnings: list[str] = []
        for i, row in enumerate(reader, start=2):
            transfer_type = (row.get("Transfer Type") or "").strip().upper()
            if transfer_type in _SKIP_TRANSFER_TYPES:
                continue  # asset leg of a trade — already captured by the cash leg
            try:
                draft = self._row_to_draft(row)
                if draft is not None:
                    drafts.append(draft)
            except Exception as exc:  # noqa: BLE001 - keep importing other rows
                warnings.append(f"Row {i}: {exc}")

        return ParseResult(
            drafts=drafts,
            detected_columns=headers,
            column_mapping={"_parser": "bux"},
            warnings=warnings,
        )

    def _row_to_draft(self, row: dict) -> TransactionDraft | None:
        category = (row.get("Transaction Category") or "").strip().lower()
        # Collapse internal double spaces ("Buy  Trade" appears in real exports).
        tx_type_raw = re.sub(r"\s+", " ", (row.get("Transaction Type") or "").strip())
        transfer = (row.get("Transfer Type") or "").strip().upper()

        trade_date = _parse_date(row.get("Transaction Time (CET)"))
        if trade_date is None:
            raise ValueError("unparseable transaction time")

        tx_type = self._map_type(category, tx_type_raw, transfer)
        if tx_type is None:
            # Unknown/asset-movement row → let the import preview flag it for review.
            return TransactionDraft(
                trade_date=trade_date,
                type=None,
                note=f"BUX: {category}/{tx_type_raw}/{transfer}",
                raw=dict(row),
            )

        asset_id = (row.get("Asset Id") or "").strip() or None
        isin = asset_id if asset_id and _ISIN_RE.match(asset_id) else None
        ticker = None if isin else asset_id

        exchange_rate = _dec(row.get("Exchange Rate"))
        asset_currency = (row.get("Asset Currency") or "").strip().upper() or "EUR"
        # Rate to EUR base: pair is EUR<asset_ccy>, Exchange Rate = asset_ccy per EUR.
        fx_to_eur = (Decimal(1) / exchange_rate) if (exchange_rate and exchange_rate != 0) else Decimal(1)

        external_id = _extract_order_id(row.get("Transaction Description"))

        if tx_type == TransactionType.DIVIDEND:
            return self._dividend_draft(row, trade_date, isin, ticker, fx_to_eur, external_id)

        if tx_type in (TransactionType.BUY, TransactionType.SELL):
            return self._trade_draft(
                row, trade_date, tx_type, isin, ticker, asset_currency, fx_to_eur, external_id
            )

        # FEE / TAX / DEPOSIT / WITHDRAWAL — cash-only transactions.
        amount = _dec(row.get("Transaction Amount")) or Decimal(0)
        return TransactionDraft(
            trade_date=trade_date,
            type=tx_type,
            ticker=ticker,
            isin=isin,
            name=(row.get("Asset Name") or "").strip() or None,
            gross_amount=abs(amount),
            fee=abs(amount) if tx_type == TransactionType.FEE else Decimal(0),
            tax=abs(amount) if tx_type == TransactionType.TAX else Decimal(0),
            currency=(row.get("Transaction Currency") or "EUR").strip().upper()[:3],
            fx_rate=Decimal(1),
            external_id=external_id,
            note=(row.get("Transaction Description") or "").strip() or None,
            raw=dict(row),
        )

    def _trade_draft(
        self, row, trade_date, tx_type, isin, ticker, asset_currency, fx_to_eur, external_id
    ) -> TransactionDraft:
        quantity = _dec(row.get("Asset Quantity"))
        price = _dec(row.get("Asset Price"))
        gross = (quantity * price) if (quantity is not None and price is not None) else None
        return TransactionDraft(
            trade_date=trade_date,
            type=tx_type,
            ticker=ticker,
            isin=isin,
            name=(row.get("Asset Name") or "").strip() or None,
            quantity=abs(quantity) if quantity is not None else None,
            price=price,
            gross_amount=abs(gross) if gross is not None else None,
            fee=Decimal(0),  # BUX books fees as separate Trading Fee rows
            tax=Decimal(0),
            currency=asset_currency[:3],
            fx_rate=fx_to_eur,
            external_id=external_id,
            raw=dict(row),
        )

    def _dividend_draft(
        self, row, trade_date, isin, ticker, fx_to_eur, external_id
    ) -> TransactionDraft:
        div_ccy = (row.get("Dividend Currency") or row.get("Transaction Currency") or "EUR").strip().upper()
        gross = _dec(row.get("Dividend Gross Amount"))
        tax = _dec(row.get("Dividend Tax Amount")) or Decimal(0)
        if gross is None:
            # Fall back to the EUR cash amount (net) when no dividend detail exists.
            gross = abs(_dec(row.get("Transaction Amount")) or Decimal(0))
            div_ccy = (row.get("Transaction Currency") or "EUR").strip().upper()
            fx_to_eur = Decimal(1)
        return TransactionDraft(
            trade_date=trade_date,
            type=TransactionType.DIVIDEND,
            ticker=ticker,
            isin=isin,
            name=(row.get("Asset Name") or "").strip() or None,
            gross_amount=gross,
            tax=tax,
            currency=div_ccy[:3],
            fx_rate=fx_to_eur,
            external_id=external_id,
            note=(row.get("Transaction Description") or "").strip() or None,
            raw=dict(row),
        )

    @staticmethod
    def _map_type(category: str, tx_type: str, transfer: str) -> TransactionType | None:
        t = tx_type.lower()
        if category == "trades":
            if t.startswith("buy"):
                return TransactionType.BUY
            if t.startswith("sell"):
                return TransactionType.SELL
            return None
        if category == "dividends":
            # Reversal is a negative dividend; still classified as DIVIDEND.
            return TransactionType.DIVIDEND
        if category == "fees":
            return TransactionType.FEE
        if category == "tax":
            # Tob (beurstaks), Financial Transaction Tax, and refunds.
            return TransactionType.TAX
        if category == "deposits":
            return TransactionType.DEPOSIT
        if category in ("interest", "others"):
            # Income / promo / lending revenue → cash inflow (documented mapping).
            if transfer == "CASH_CREDIT":
                return TransactionType.DEPOSIT
            if transfer == "CASH_DEBIT":
                return TransactionType.WITHDRAWAL
            return None  # asset transfers → flagged for manual review
        if category == "corporate_actions":
            if transfer == "CASH_CREDIT":
                return TransactionType.DEPOSIT
            return None  # ASSET_REDEEM / ASSET_DEPOSIT → manual review
        return None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _dec(value: str | None) -> Decimal | None:
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _extract_order_id(description: str | None) -> str | None:
    if not description:
        return None
    m = _ORDER_ID_RE.search(description)
    return m.group(1) if m else None

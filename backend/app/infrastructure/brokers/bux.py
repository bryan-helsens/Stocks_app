"""BUX statement parser.

BUX exports are CSV-based; this parser layers BUX-specific recognition on top of
the generic CSV parser. Because the exact BUX column layout can vary by export
type and will be confirmed against the user's sample files, the parser leans on
the shared synonym detection and only adds BUX-specific hints and recognition.

To adapt to the real BUX sample files: extend ``_BUX_SYNONYM_HINTS`` and, if the
export is not comma-delimited or has a preamble, override :meth:`parse`.
"""

from __future__ import annotations

from app.domain.ports.broker_parser import ParseResult
from app.infrastructure.brokers.csv_generic import CsvGenericParser

# Extra header hints observed in BUX exports, merged into detection upstream if
# needed. Kept here so BUX-specific tweaks live with the BUX adapter.
_BUX_SYNONYM_HINTS: dict[str, list[str]] = {
    "trade_date": ["transaction time", "executed at", "date"],
    "type": ["transaction type", "type"],
    "name": ["asset name", "product name", "name"],
    "ticker": ["asset", "symbol", "ticker"],
    "quantity": ["amount of shares", "number of shares", "quantity"],
    "price": ["price per share", "share price", "price"],
    "gross_amount": ["total amount", "amount", "value"],
    "fee": ["transaction cost", "fee", "costs"],
    "currency": ["currency"],
}


class BuxParser:
    parser_key = "bux"

    def __init__(self) -> None:
        self._csv = CsvGenericParser()

    def can_parse(self, filename: str, sample: bytes) -> bool:
        name = filename.lower()
        if "bux" in name and name.endswith(".csv"):
            return True
        # Sniff a few BUX-typical header tokens.
        head = sample[:2048].decode("utf-8", errors="ignore").lower()
        tokens = ("bux", "amount of shares", "price per share", "transaction type")
        return name.endswith(".csv") and any(t in head for t in tokens)

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        # Delegate the heavy lifting to the generic CSV parser; the synonym
        # dictionary already recognises BUX-style headers. A user mapping (from
        # the import preview) takes precedence.
        result = self._csv.parse(content, column_mapping=column_mapping)
        # Tag the source so downstream knows it's BUX.
        for draft in result.drafts:
            draft.raw.setdefault("_source_broker", "bux")
        return result

"""Broker statement parser registry (generic import framework, M4).

Registering a new broker is as simple as implementing
:class:`app.domain.ports.broker_parser.BrokerStatementParser` and adding it to
``_PARSERS`` below — no other part of the system changes (FR4.6).

``select_parser`` chooses a parser by explicit key (from the UI's "source"
choice) or by auto-detection against the uploaded file.
"""

from __future__ import annotations

from app.domain.ports.broker_parser import BrokerStatementParser
from app.infrastructure.brokers.bux import BuxParser
from app.infrastructure.brokers.csv_generic import CsvGenericParser
from app.infrastructure.brokers.excel import ExcelParser
from app.infrastructure.brokers.pdf import PdfParser

# Order matters for auto-detection: more specific parsers first.
_PARSERS: list[BrokerStatementParser] = [
    BuxParser(),
    ExcelParser(),
    PdfParser(),
    CsvGenericParser(),  # generic fallback last
]

_BY_KEY: dict[str, BrokerStatementParser] = {p.parser_key: p for p in _PARSERS}


def get_parser(parser_key: str) -> BrokerStatementParser | None:
    """Return the parser registered under *parser_key*, if any."""
    return _BY_KEY.get(parser_key)


def select_parser(
    filename: str, sample: bytes, parser_key: str | None = None
) -> BrokerStatementParser | None:
    """Pick a parser: explicit *parser_key* wins, else auto-detect by content."""
    if parser_key:
        chosen = _BY_KEY.get(parser_key)
        if chosen is not None:
            return chosen
    for parser in _PARSERS:
        try:
            if parser.can_parse(filename, sample):
                return parser
        except Exception:  # noqa: BLE001 - detection must never crash selection
            continue
    return None


def available_parsers() -> list[str]:
    return list(_BY_KEY.keys())

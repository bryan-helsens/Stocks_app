"""Port for broker statement parsers (generic import framework, M4).

A parser turns a raw uploaded file (BUX/CSV/Excel/PDF) into a list of
:class:`TransactionDraft` rows in a canonical shape. Classification,
enrichment, deduplication and persistence happen in the import pipeline
(application layer) — a parser only needs to *extract and normalise*. Adding a
new broker therefore means implementing this Protocol and registering it; no
core change is required (architecture principle #3, BR/FR4.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.domain.value_objects.enums import TransactionType


@dataclass(slots=True)
class TransactionDraft:
    """Canonical, broker-agnostic representation of one parsed row."""

    trade_date: datetime
    type: TransactionType | None  # None => let the pipeline classify
    ticker: str | None = None
    isin: str | None = None
    name: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gross_amount: Decimal | None = None
    fee: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    currency: str = "EUR"
    fx_rate: Decimal | None = None
    external_id: str | None = None
    note: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    """Output of a parser run."""

    drafts: list[TransactionDraft]
    detected_columns: list[str] = field(default_factory=list)
    column_mapping: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class BrokerStatementParser(Protocol):
    """Parses a raw statement into canonical transaction drafts."""

    #: Stable key used to register/look up the parser (e.g. "bux", "csv_generic").
    parser_key: str

    def can_parse(self, filename: str, sample: bytes) -> bool:
        """Return True if this parser recognises the given file."""
        ...

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        """Parse *content* into drafts, optionally guided by a user mapping."""
        ...

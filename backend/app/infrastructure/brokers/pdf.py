"""PDF statement parser (best-effort table extraction).

PDF layouts vary widely, so this parser extracts text lines and attempts to
recover a delimited table, then defers to the generic CSV pipeline. When a
statement is not tabular, rows are flagged as warnings for manual entry. The
import preview lets the user correct anything before commit (FR4.5).
"""

from __future__ import annotations

import re

from app.domain.ports.broker_parser import ParseResult, TransactionDraft
from app.infrastructure.brokers.csv_generic import CsvGenericParser

_WHITESPACE_COLUMNS = re.compile(r"\s{2,}")


class PdfParser:
    parser_key = "pdf"

    def __init__(self) -> None:
        self._csv = CsvGenericParser()

    def can_parse(self, filename: str, sample: bytes) -> bool:
        return filename.lower().endswith(".pdf") or sample[:5] == b"%PDF-"

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        try:
            text = self._extract_text(content)
        except Exception as exc:  # noqa: BLE001
            return ParseResult(drafts=[], warnings=[f"Could not read PDF: {exc}"])

        # Convert multi-space-separated columns into a pseudo-CSV.
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            return ParseResult(drafts=[], warnings=["PDF contained no extractable text"])

        csv_lines = [";".join(_WHITESPACE_COLUMNS.split(ln.strip())) for ln in lines]
        pseudo_csv = "\n".join(csv_lines).encode("utf-8")
        result = self._csv.parse(pseudo_csv, column_mapping=column_mapping)
        result.warnings.insert(
            0, "PDF parsing is best-effort; please review the preview carefully."
        )
        return result

    @staticmethod
    def _extract_text(content: bytes) -> str:
        # pypdf is an optional dependency; import lazily so the app starts
        # without it and the error is surfaced only when a PDF is uploaded.
        import io

        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    @staticmethod
    def _empty() -> ParseResult:
        return ParseResult(drafts=[], warnings=[])

    @staticmethod
    def _manual(draft: TransactionDraft) -> TransactionDraft:
        return draft

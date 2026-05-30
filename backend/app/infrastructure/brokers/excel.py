"""Excel (.xlsx) statement parser.

Reads the first worksheet into rows and reuses the generic CSV pipeline by
converting the sheet to CSV in memory, so column detection, classification and
number parsing are shared.
"""

from __future__ import annotations

import csv
import io

from app.domain.ports.broker_parser import ParseResult
from app.infrastructure.brokers.csv_generic import CsvGenericParser


class ExcelParser:
    parser_key = "excel"

    def __init__(self) -> None:
        self._csv = CsvGenericParser()

    def can_parse(self, filename: str, sample: bytes) -> bool:
        return filename.lower().endswith((".xlsx", ".xlsm"))

    def parse(
        self, content: bytes, *, column_mapping: dict[str, str] | None = None
    ) -> ParseResult:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for row in ws.iter_rows(values_only=True):
            writer.writerow(["" if c is None else c for c in row])
        wb.close()
        return self._csv.parse(buffer.getvalue().encode("utf-8"), column_mapping=column_mapping)

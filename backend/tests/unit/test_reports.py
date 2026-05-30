"""Unit tests for the report document renderers (CSV / JSON / Excel)."""

from __future__ import annotations

import json

from app.domain.value_objects.enums import ReportFormat
from app.infrastructure.reports.document import ReportDocument, Section, Table
from app.infrastructure.reports.renderers import render


def _doc() -> ReportDocument:
    doc = ReportDocument(title="Portefeuillerapport", subtitle="Test")
    doc.add_section(
        Section(
            heading="Overzicht",
            facts={"Totale waarde": "1000.00 EUR"},
            tables=[Table(title="Holdings", headers=["Ticker", "Aantal"], rows=[["AAPL", "10"]])],
        )
    )
    return doc


def test_json_render_roundtrip():
    content, mime = render(_doc(), ReportFormat.JSON)
    assert mime == "application/json"
    data = json.loads(content)
    assert data["title"] == "Portefeuillerapport"
    assert data["sections"][0]["facts"]["Totale waarde"] == "1000.00 EUR"
    assert data["disclaimer"]  # always present


def test_csv_render_contains_data():
    content, mime = render(_doc(), ReportFormat.CSV)
    assert mime == "text/csv"
    text = content.decode("utf-8")
    assert "Portefeuillerapport" in text
    assert "AAPL" in text
    assert "Disclaimer" in text


def test_excel_render_is_xlsx():
    content, mime = render(_doc(), ReportFormat.EXCEL)
    assert "spreadsheetml" in mime
    # XLSX files are ZIP archives starting with 'PK'.
    assert content[:2] == b"PK"

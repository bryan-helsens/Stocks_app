"""Heuristic column detection for tabular broker statements.

Maps arbitrary, multi-language column headers to canonical fields using a
synonym dictionary and fuzzy normalisation. Shared by the generic CSV/Excel
parsers so that "Datum", "Trade Date", "Date d'opération" all map to
``trade_date``. This powers FR4.2 (automatic column recognition).
"""

from __future__ import annotations

import re

# Canonical field -> list of lowercased header synonyms (NL/EN/FR).
SYNONYMS: dict[str, list[str]] = {
    "trade_date": ["date", "datum", "trade date", "transaction date", "boekdatum",
                   "uitvoeringsdatum", "value date", "date d'operation", "execution date"],
    "type": ["type", "transaction type", "soort", "transactietype", "action",
             "order type", "side", "buy/sell", "categorie", "category"],
    "ticker": ["ticker", "symbol", "symbool", "instrument", "stock", "aandeel"],
    "isin": ["isin", "isin code", "isin-code"],
    "name": ["name", "naam", "description", "omschrijving", "product", "security",
             "company", "bedrijf", "libelle"],
    "quantity": ["quantity", "aantal", "qty", "shares", "units", "stuks", "volume",
                 "number of shares", "quantite"],
    "price": ["price", "prijs", "koers", "unit price", "price per share",
              "stockprice", "cours", "share price"],
    "gross_amount": ["amount", "bedrag", "total", "totaal", "value", "waarde",
                     "gross", "bruto", "montant", "total amount", "transaction amount"],
    "fee": ["fee", "fees", "commission", "kosten", "transactiekosten", "courtage",
            "commissie", "frais", "charge"],
    "tax": ["tax", "taks", "belasting", "tob", "beurstaks", "withholding",
            "roerende voorheffing", "stamp duty", "impot"],
    "currency": ["currency", "valuta", "munt", "ccy", "devise"],
    "fx_rate": ["fx", "fx rate", "exchange rate", "wisselkoers", "rate", "koers eur",
                "taux de change"],
    "external_id": ["id", "order id", "transaction id", "reference", "referentie",
                    "ordernr", "trade id", "execution id"],
}


def _normalize(header: str) -> str:
    """Lowercase, strip accents-ish and collapse non-alphanumerics to spaces."""
    h = header.strip().lower()
    h = re.sub(r"[_\-./]+", " ", h)
    h = re.sub(r"\s+", " ", h)
    return h.strip()


def detect_mapping(headers: list[str]) -> dict[str, str]:
    """Return a mapping ``{original_header: canonical_field}``.

    Exact synonym matches win; otherwise a substring match is attempted. Each
    canonical field is assigned at most once (first matching header).
    """
    mapping: dict[str, str] = {}
    used_fields: set[str] = set()
    normalized = {h: _normalize(h) for h in headers}

    # Pass 1: exact synonym match.
    for header, norm in normalized.items():
        for field, syns in SYNONYMS.items():
            if field in used_fields:
                continue
            if norm in syns:
                mapping[header] = field
                used_fields.add(field)
                break

    # Pass 2: substring / token match for remaining headers.
    for header, norm in normalized.items():
        if header in mapping:
            continue
        for field, syns in SYNONYMS.items():
            if field in used_fields:
                continue
            if any(syn in norm or norm in syn for syn in syns):
                mapping[header] = field
                used_fields.add(field)
                break

    return mapping

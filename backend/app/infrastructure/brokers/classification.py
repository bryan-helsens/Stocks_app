"""Transaction-type classification from raw row hints (FR4.3).

When a statement does not carry an explicit, recognisable type, infer it from
keywords and numeric signs. Multi-language keyword sets cover NL/EN/FR.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.value_objects.enums import TransactionType

_KEYWORDS: dict[TransactionType, list[str]] = {
    TransactionType.BUY: ["buy", "koop", "aankoop", "purchase", "achat", "bought"],
    TransactionType.SELL: ["sell", "verkoop", "sale", "vente", "sold"],
    TransactionType.DIVIDEND: ["dividend", "dividende", "coupon", "distribution"],
    TransactionType.FEE: ["fee", "kosten", "commission", "courtage", "frais", "charge"],
    TransactionType.TAX: ["tax", "taks", "belasting", "voorheffing", "tob", "impot",
                          "withholding"],
    TransactionType.DEPOSIT: ["deposit", "storting", "inleg", "top up", "funding",
                              "depot", "transfer in"],
    TransactionType.WITHDRAWAL: ["withdraw", "opname", "uitbetaling", "retrait",
                                 "transfer out", "payout"],
    TransactionType.STOCK_SPLIT: ["split", "stock split", "aandelensplitsing"],
    TransactionType.REVERSE_SPLIT: ["reverse split", "omgekeerde split"],
}


def classify(
    raw_type: str | None,
    *,
    has_asset: bool,
    quantity: Decimal | None,
    amount: Decimal | None,
) -> TransactionType | None:
    """Best-effort classification of a row into a :class:`TransactionType`.

    Args:
        raw_type: the statement's own type/description text, if any.
        has_asset: whether the row references a security.
        quantity: parsed quantity (sign can hint buy vs sell).
        amount: parsed amount (sign can hint deposit vs withdrawal).

    Returns:
        The inferred type, or ``None`` when it cannot be determined (the row is
        then flagged INVALID for manual mapping).
    """
    text = (raw_type or "").lower()
    for tx_type, words in _KEYWORDS.items():
        if any(w in text for w in words):
            return tx_type

    # Fall back to structural heuristics.
    if has_asset and quantity is not None:
        if quantity > 0:
            return TransactionType.BUY
        if quantity < 0:
            return TransactionType.SELL
    if not has_asset and amount is not None:
        return TransactionType.DEPOSIT if amount > 0 else TransactionType.WITHDRAWAL
    return None

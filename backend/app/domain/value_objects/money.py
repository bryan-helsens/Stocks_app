"""Money value object.

Financial amounts are represented with :class:`decimal.Decimal` (never floats)
to avoid binary rounding errors. ``Money`` couples an amount with an ISO-4217
currency and forbids silent cross-currency arithmetic — conversions must go
through an explicit exchange rate.

This module is pure (no I/O, no framework imports) and fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

# Internal storage precision. Presentation rounds to currency minor units.
_QUANT = Decimal("0.00000001")  # 8 dp, matches NUMERIC(20,8)


def to_decimal(value: Any) -> Decimal:
    """Coerce *value* to Decimal safely (rejects float NaN/inf and junk)."""
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, (int, str)):
        try:
            d = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid numeric value: {value!r}") from exc
    elif isinstance(value, float):
        # Route through str to avoid binary artefacts (0.1 -> 0.1000000000...).
        d = Decimal(str(value))
    else:
        raise TypeError(f"Cannot convert {type(value).__name__} to Decimal")
    if not d.is_finite():
        raise ValueError("Money amount must be finite")
    return d.quantize(_QUANT, rounding=ROUND_HALF_EVEN)


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic is attempted between differing currencies."""


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable (amount, currency) pair.

    Arithmetic is only allowed between identical currencies; use
    :meth:`convert` for cross-currency operations.
    """

    amount: Decimal
    currency: str

    def __init__(self, amount: Any, currency: str) -> None:
        if not isinstance(currency, str) or len(currency) != 3:
            raise ValueError(f"Currency must be a 3-letter ISO code, got {currency!r}")
        object.__setattr__(self, "amount", to_decimal(amount))
        object.__setattr__(self, "currency", currency.upper())

    # ----- factories -----------------------------------------------------
    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal(0), currency)

    # ----- guards --------------------------------------------------------
    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot operate on {self.currency} and {other.currency}"
            )

    # ----- arithmetic ----------------------------------------------------
    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Any) -> Money:
        return Money(self.amount * to_decimal(factor), self.currency)

    def __truediv__(self, divisor: Any) -> Money:
        d = to_decimal(divisor)
        if d == 0:
            raise ZeroDivisionError("Division of Money by zero")
        return Money(self.amount / d, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    # ----- comparisons ---------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    # ----- predicates ----------------------------------------------------
    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    # ----- conversion ----------------------------------------------------
    def convert(self, to_currency: str, rate: Any) -> Money:
        """Convert to *to_currency* using *rate* (units of target per unit of self)."""
        return Money(self.amount * to_decimal(rate), to_currency)

    # ----- presentation --------------------------------------------------
    def rounded(self, places: int = 2) -> Decimal:
        """Return the amount rounded to *places* (bankers' rounding)."""
        q = Decimal(1).scaleb(-places)
        return self.amount.quantize(q, rounding=ROUND_HALF_EVEN)

    def format(self, places: int = 2) -> str:
        return f"{self.rounded(places)} {self.currency}"

    def __str__(self) -> str:
        return self.format()

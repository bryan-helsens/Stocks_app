"""Domain enumerations.

These mirror the PostgreSQL enum types in ``db/schema.sql`` and are the single
source of truth used across the domain, application and API layers. Keeping
them as plain ``str`` enums makes (de)serialisation trivial.
"""

from __future__ import annotations

from enum import StrEnum


class AssetClass(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    REIT = "REIT"
    BOND = "BOND"
    CASH = "CASH"
    CRYPTO = "CRYPTO"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    FEE = "FEE"
    TAX = "TAX"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"


class TransactionSource(StrEnum):
    MANUAL = "MANUAL"
    IMPORT_CSV = "IMPORT_CSV"
    IMPORT_EXCEL = "IMPORT_EXCEL"
    IMPORT_PDF = "IMPORT_PDF"
    IMPORT_BUX = "IMPORT_BUX"
    API = "API"


class ImportStatus(StrEnum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    PREVIEWED = "PREVIEWED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class ImportRowStatus(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"
    COMMITTED = "COMMITTED"


class Recommendation(StrEnum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"


class ValuationVerdict(StrEnum):
    UNDERVALUED = "UNDERVALUED"
    FAIR = "FAIR"
    OVERVALUED = "OVERVALUED"


class ValuationMethod(StrEnum):
    DCF = "DCF"
    DDM = "DDM"
    MULTIPLES = "MULTIPLES"
    BLENDED = "BLENDED"


class AlertType(StrEnum):
    PRICE_TARGET = "PRICE_TARGET"
    FAIR_VALUE = "FAIR_VALUE"
    DIVIDEND_RECEIVED = "DIVIDEND_RECEIVED"
    EX_DIVIDEND = "EX_DIVIDEND"
    RISK = "RISK"
    PRICE_MOVE = "PRICE_MOVE"
    OVERVALUED = "OVERVALUED"
    UNDERVALUED = "UNDERVALUED"


class AlertChannel(StrEnum):
    PUSH = "PUSH"
    TELEGRAM = "TELEGRAM"
    EMAIL = "EMAIL"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


class FireType(StrEnum):
    LEAN = "LEAN"
    COAST = "COAST"
    BARISTA = "BARISTA"
    FAT = "FAT"


class AIProvider(StrEnum):
    OPENAI = "OPENAI"
    CLAUDE = "CLAUDE"
    OLLAMA = "OLLAMA"


class ReportType(StrEnum):
    PORTFOLIO = "PORTFOLIO"
    DIVIDEND = "DIVIDEND"
    ANNUAL = "ANNUAL"
    TAX = "TAX"
    FIRE = "FIRE"
    RISK = "RISK"
    ALLOCATION = "ALLOCATION"
    AI = "AI"


class ReportFormat(StrEnum):
    PDF = "PDF"
    CSV = "CSV"
    EXCEL = "EXCEL"
    JSON = "JSON"


class ReportStatus(StrEnum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class DividendKind(StrEnum):
    CONFIRMED = "CONFIRMED"
    PROJECTED = "PROJECTED"


class CostBasisMethod(StrEnum):
    FIFO = "FIFO"
    LIFO = "LIFO"
    AVERAGE = "AVERAGE"

"""Format-agnostic report document model.

A :class:`ReportDocument` is built once by the application layer (from portfolio,
dividend, tax, FIRE, etc. data) and then rendered to PDF / CSV / Excel / JSON by
the renderers in this package. This keeps report *content* separate from report
*format* (deliverable 12). Every document carries the educational disclaimer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.common import DISCLAIMER_NL


@dataclass(slots=True)
class Table:
    """A simple tabular block: a header row plus data rows (all stringifiable)."""

    title: str
    headers: list[str]
    rows: list[list[str]]


@dataclass(slots=True)
class Section:
    """A titled section with optional key/value facts and tables."""

    heading: str
    facts: dict[str, str] = field(default_factory=dict)
    tables: list[Table] = field(default_factory=list)
    text: str | None = None


@dataclass(slots=True)
class ReportDocument:
    """The complete, render-ready report."""

    title: str
    subtitle: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)
    sections: list[Section] = field(default_factory=list)
    disclaimer: str = DISCLAIMER_NL

    def add_section(self, section: Section) -> Section:
        self.sections.append(section)
        return section

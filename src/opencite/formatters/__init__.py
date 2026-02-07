"""Output formatters for opencite."""

from __future__ import annotations

from opencite.formatters.base import OutputFormatter
from opencite.formatters.bibtex_fmt import BibtexFormatter
from opencite.formatters.csv_fmt import CsvFormatter
from opencite.formatters.json_fmt import JsonFormatter
from opencite.formatters.text import TextFormatter


def get_formatter(fmt: str) -> OutputFormatter:
    """Return the appropriate formatter for the given format string."""
    if fmt == "json":
        return JsonFormatter()
    if fmt == "bibtex":
        return BibtexFormatter()
    if fmt == "csv":
        return CsvFormatter()
    return TextFormatter()


__all__ = [
    "OutputFormatter",
    "TextFormatter",
    "JsonFormatter",
    "BibtexFormatter",
    "CsvFormatter",
    "get_formatter",
]

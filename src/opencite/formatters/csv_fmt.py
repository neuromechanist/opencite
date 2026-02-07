"""CSV output formatter."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from opencite.formatters.base import OutputFormatter

if TYPE_CHECKING:
    from opencite.models import Paper

_FIELDS = [
    "title",
    "authors",
    "year",
    "doi",
    "pmid",
    "pmcid",
    "journal",
    "citation_count",
    "url",
    "is_oa",
    "data_sources",
]


class CsvFormatter(OutputFormatter):
    """Format papers as CSV output."""

    def format_papers(
        self, papers: list[Paper], verbose: bool = False  # noqa: ARG002
    ) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_FIELDS)
        writer.writeheader()
        for paper in papers:
            writer.writerow(_paper_to_row(paper))
        return buf.getvalue().rstrip("\n")

    def format_single(self, paper: Paper, verbose: bool = False) -> str:  # noqa: ARG002
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_FIELDS)
        writer.writeheader()
        writer.writerow(_paper_to_row(paper))
        return buf.getvalue().rstrip("\n")


def _paper_to_row(paper: Paper) -> dict[str, str]:
    """Convert a Paper to a CSV-compatible dict."""
    authors = "; ".join(a.name for a in paper.authors)
    return {
        "title": paper.title,
        "authors": authors,
        "year": paper.year_str,
        "doi": paper.doi,
        "pmid": paper.pmid,
        "pmcid": paper.pmcid,
        "journal": paper.journal,
        "citation_count": str(paper.citation_count),
        "url": paper.url,
        "is_oa": str(paper.is_oa),
        "data_sources": ", ".join(sorted(paper.data_sources)),
    }

"""BibTeX output formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opencite.bibtex import generate_bibtex
from opencite.formatters.base import OutputFormatter

if TYPE_CHECKING:
    from opencite.models import Paper


class BibtexFormatter(OutputFormatter):
    """Format papers as BibTeX entries.

    Uses cached BibTeX from S2 if available, otherwise generates
    from paper metadata. For DOI content negotiation (higher quality),
    use ``bibtex.fetch_bibtex()`` before formatting.
    """

    def format_papers(
        self, papers: list[Paper], verbose: bool = False  # noqa: ARG002
    ) -> str:
        entries = [_get_bibtex(p) for p in papers]
        return "\n\n".join(entries)

    def format_single(self, paper: Paper, verbose: bool = False) -> str:  # noqa: ARG002
        return _get_bibtex(paper)


def _get_bibtex(paper: Paper) -> str:
    """Return cached BibTeX or generate from metadata."""
    if paper._bibtex:
        return paper._bibtex
    return generate_bibtex(paper)

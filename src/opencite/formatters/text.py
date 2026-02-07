"""Human-readable text output formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opencite.formatters.base import OutputFormatter

if TYPE_CHECKING:
    from opencite.models import Paper


class TextFormatter(OutputFormatter):
    """Format papers as readable text output."""

    def format_papers(
        self, papers: list[Paper], verbose: bool = False
    ) -> str:
        if not papers:
            return "No results found."

        lines = []
        lines.append(f"{'=' * 80}")
        lines.append(f"  {len(papers)} result{'s' if len(papers) != 1 else ''}")
        lines.append(f"{'=' * 80}")
        lines.append("")

        for i, paper in enumerate(papers, 1):
            lines.append(self._format_entry(i, paper, verbose))

        return "\n".join(lines)

    def format_single(self, paper: Paper, verbose: bool = False) -> str:
        return self._format_entry(1, paper, verbose)

    def _format_entry(
        self, index: int, paper: Paper, verbose: bool = False
    ) -> str:
        parts = []

        # Title line
        year_str = f" ({paper.year_str})" if paper.year else ""
        parts.append(f"[{index}] {paper.authors_short}{year_str} {paper.title}")

        # Source/DOI/Citations line
        sources = ", ".join(sorted(paper.data_sources))
        meta = [f"Source: {sources}"]
        if paper.doi:
            meta.append(f"DOI: {paper.doi}")
        if paper.citation_count:
            meta.append(f"Cited: {paper.citation_count}")
        parts.append(f"    {' | '.join(meta)}")

        # Journal
        if paper.journal:
            parts.append(f"    Journal: {paper.journal}")

        # URL
        if paper.url:
            parts.append(f"    {paper.url}")

        # IDs
        id_parts = []
        if paper.pmid:
            id_parts.append(f"PMID: {paper.pmid}")
        if paper.pmcid:
            id_parts.append(f"PMCID: {paper.pmcid}")
        if paper.ids.openalex_id:
            id_parts.append(f"OpenAlex: {paper.ids.openalex_id}")
        if id_parts:
            parts.append(f"    {' | '.join(id_parts)}")

        # Verbose: abstract, TLDR
        if verbose:
            if paper.tldr:
                parts.append(f"    TLDR: {paper.tldr}")
            if paper.abstract:
                display = paper.abstract[:300]
                if len(paper.abstract) > 300:
                    display += "..."
                parts.append(f"    Abstract: {display}")

        parts.append("")
        return "\n".join(parts)

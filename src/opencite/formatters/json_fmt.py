"""JSON output formatter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from opencite.formatters.base import OutputFormatter

if TYPE_CHECKING:
    from opencite.models import Paper


class JsonFormatter(OutputFormatter):
    """Format papers as JSON output."""

    def format_papers(self, papers: list[Paper], verbose: bool = False) -> str:
        data = [_paper_to_dict(p, verbose) for p in papers]
        return json.dumps(data, indent=2, ensure_ascii=False)

    def format_single(self, paper: Paper, verbose: bool = False) -> str:
        data = _paper_to_dict(paper, verbose)
        return json.dumps(data, indent=2, ensure_ascii=False)


def _paper_to_dict(paper: Paper, verbose: bool = False) -> dict:
    """Convert a Paper to a JSON-serializable dict."""
    d: dict = {
        "title": paper.title,
        "authors": [
            {
                "name": a.name,
                "family_name": a.family_name,
                "given_name": a.given_name,
            }
            for a in paper.authors
        ],
        "year": paper.year,
        "ids": {
            "doi": paper.ids.doi,
            "pmid": paper.ids.pmid,
            "pmcid": paper.ids.pmcid,
            "openalex_id": paper.ids.openalex_id,
            "s2_id": paper.ids.s2_id,
            "arxiv_id": paper.ids.arxiv_id,
        },
        "citation_count": paper.citation_count,
        "url": paper.url,
        "is_oa": paper.is_oa,
        "data_sources": sorted(paper.data_sources),
    }

    if paper.journal:
        d["journal"] = paper.journal
    if paper.publication_date:
        d["publication_date"] = paper.publication_date
    if paper.pub_type:
        d["pub_type"] = paper.pub_type
    if paper.is_retracted:
        d["is_retracted"] = True

    if verbose:
        if paper.abstract:
            d["abstract"] = paper.abstract
        if paper.tldr:
            d["tldr"] = paper.tldr
        if paper.topics:
            d["topics"] = paper.topics
        if paper.mesh_terms:
            d["mesh_terms"] = paper.mesh_terms
        if paper.pdf_locations:
            d["pdf_locations"] = [
                {"url": loc.url, "source": loc.source, "is_oa": loc.is_oa}
                for loc in paper.pdf_locations
            ]
        if paper.grants:
            d["grants"] = paper.grants

    return d

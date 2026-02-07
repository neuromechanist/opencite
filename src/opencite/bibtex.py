"""BibTeX fetch and generation utilities."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from opencite.models import Paper


async def fetch_bibtex(paper: Paper) -> str:
    """Get BibTeX for a paper, trying multiple sources.

    Priority:
    1. Cached BibTeX from S2 citationStyles
    2. DOI content negotiation
    3. Generate from metadata
    """
    if paper._bibtex:
        return paper._bibtex

    if paper.doi:
        bib = await fetch_bibtex_from_doi(paper.doi)
        if bib:
            return bib

    return generate_bibtex(paper)


async def fetch_bibtex_from_doi(doi: str) -> str:
    """Fetch official BibTeX from doi.org using content negotiation."""
    if not doi:
        return ""
    url = f"https://doi.org/{doi}"
    headers = {"Accept": "application/x-bibtex; charset=utf-8"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            bib = resp.text.strip()
            if bib.startswith("@"):
                return bib
    except Exception:
        pass
    return ""


def generate_bibtex(paper: Paper) -> str:
    """Generate a BibTeX entry from Paper metadata."""
    cite_key = _make_cite_key(paper)
    bib_authors = _format_authors_bibtex(paper)

    entry_type = "article"
    fields = []
    fields.append(f"  title = {{{paper.title}}}")
    if bib_authors:
        fields.append(f"  author = {{{bib_authors}}}")
    if paper.journal:
        fields.append(f"  journal = {{{paper.journal}}}")
    if paper.year:
        fields.append(f"  year = {{{paper.year}}}")
    if paper.doi:
        fields.append(f"  doi = {{{paper.doi}}}")
    if paper.url:
        fields.append(f"  url = {{{paper.url}}}")

    return f"@{entry_type}{{{cite_key},\n" + ",\n".join(fields) + "\n}"


def _make_cite_key(paper: Paper) -> str:
    """Generate a citation key: lastname + year + first title word."""
    last_name = "unknown"
    if paper.authors:
        a = paper.authors[0]
        raw = a.family_name or a.name.split(",")[0].strip()
        last_name = re.sub(r"[^a-zA-Z]", "", raw).lower() or "unknown"

    year = paper.year or ""

    first_word = "paper"
    if paper.title:
        words = paper.title.split()
        if words:
            first_word = re.sub(r"[^a-zA-Z]", "", words[0]).lower() or "paper"

    return f"{last_name}{year}{first_word}"


def _format_authors_bibtex(paper: Paper) -> str:
    """Format authors for BibTeX: 'Last1, First1 and Last2, First2'."""
    if not paper.authors:
        return ""
    parts = []
    for a in paper.authors:
        if a.family_name and a.given_name:
            parts.append(f"{a.family_name}, {a.given_name}")
        else:
            parts.append(a.name)
    return " and ".join(parts)

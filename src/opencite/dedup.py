"""Deduplication and merging of papers from multiple sources."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from opencite.utils import normalize_title, titles_similar

if TYPE_CHECKING:
    from opencite.models import Paper


def deduplicate(papers: list[Paper]) -> list[Paper]:
    """Deduplicate papers by DOI and fuzzy title matching, merging metadata.

    When the same paper is found by multiple APIs, the duplicates are merged
    so the resulting Paper has the richest metadata from all sources.
    """
    seen_dois: dict[str, int] = {}  # doi -> index in unique
    seen_titles: list[tuple[set[str], int]] = []  # (title_words, index)
    unique: list[Paper] = []

    for paper in papers:
        existing_idx = _find_duplicate(paper, unique, seen_dois, seen_titles)

        if existing_idx is not None:
            unique[existing_idx] = merge_papers(unique[existing_idx], paper)
        else:
            idx = len(unique)
            unique.append(paper)
            if paper.doi:
                seen_dois[paper.doi.lower()] = idx
            title_words = normalize_title(paper.title)
            if title_words:
                seen_titles.append((title_words, idx))

    return unique


def _find_duplicate(
    paper: Paper,
    unique: list[Paper],
    seen_dois: dict[str, int],
    seen_titles: list[tuple[set[str], int]],
) -> int | None:
    """Find the index of a duplicate paper, or None if no duplicate exists."""
    # Check DOI first (exact match)
    if paper.doi:
        doi_lower = paper.doi.lower()
        if doi_lower in seen_dois:
            return seen_dois[doi_lower]

    # Check PMID match against existing papers
    if paper.pmid:
        for idx, existing in enumerate(unique):
            if existing.pmid and existing.pmid == paper.pmid:
                return idx

    # Fuzzy title match
    title_words = normalize_title(paper.title)
    if title_words:
        for seen_words, idx in seen_titles:
            if titles_similar(title_words, seen_words):
                return idx

    return None


def merge_papers(existing: Paper, new: Paper) -> Paper:
    """Merge metadata from two Paper objects representing the same paper.

    Strategy:
    - Union all identifiers
    - Prefer longer abstract
    - Take TLDR from whichever has it
    - Take higher citation count
    - Union PDF locations, topics, MeSH, grants
    - Union data_sources for provenance tracking
    - Prefer more authors (richer author list)
    """
    merged_ids = existing.ids.merge(new.ids)
    merged_sources = existing.data_sources | new.data_sources

    # Prefer longer abstract
    abstract = (
        existing.abstract
        if len(existing.abstract) >= len(new.abstract)
        else new.abstract
    )

    # Take TLDR from whichever has it
    tldr = existing.tldr or new.tldr

    # Prefer more authors
    authors = (
        existing.authors if len(existing.authors) >= len(new.authors) else new.authors
    )

    # Higher citation count
    citation_count = max(existing.citation_count, new.citation_count)
    influential = max(
        existing.influential_citation_count, new.influential_citation_count
    )

    # Union PDF locations (deduplicated by URL)
    pdf_urls = {loc.url for loc in existing.pdf_locations}
    merged_pdfs = list(existing.pdf_locations)
    for loc in new.pdf_locations:
        if loc.url not in pdf_urls:
            merged_pdfs.append(loc)
            pdf_urls.add(loc.url)

    # Union topics and MeSH (preserve order, deduplicate)
    topics = _union_lists(existing.topics, new.topics)
    mesh_terms = _union_lists(existing.mesh_terms, new.mesh_terms)
    keywords = _union_lists(existing.keywords, new.keywords)

    # Union grants (simple dedup by funder+award_id)
    grants = _union_grants(existing.grants, new.grants)

    # Prefer existing venue if present, else take new
    source_venue = existing.source_venue or new.source_venue

    # BibTeX: prefer existing if present
    bibtex = existing._bibtex or new._bibtex

    return replace(
        existing,
        ids=merged_ids,
        authors=authors,
        abstract=abstract,
        tldr=tldr,
        citation_count=citation_count,
        influential_citation_count=influential,
        pdf_locations=merged_pdfs,
        topics=topics,
        mesh_terms=mesh_terms,
        keywords=keywords,
        grants=grants,
        source_venue=source_venue,
        data_sources=merged_sources,
        is_oa=existing.is_oa or new.is_oa,
        oa_status=existing.oa_status or new.oa_status,
        is_retracted=existing.is_retracted or new.is_retracted,
        year=existing.year or new.year,
        publication_date=existing.publication_date or new.publication_date,
        pub_type=existing.pub_type or new.pub_type,
        url=existing.url or new.url,
        _bibtex=bibtex,
    )


def _union_lists(a: list[str], b: list[str]) -> list[str]:
    """Union two lists preserving order, deduplicating."""
    seen: set[str] = set()
    result: list[str] = []
    for item in [*a, *b]:
        lower = item.lower()
        if lower not in seen:
            seen.add(lower)
            result.append(item)
    return result


def _union_grants(
    a: list[dict[str, str]], b: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Union grants lists, deduplicating by funder+award_id."""
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for grant in [*a, *b]:
        key = (grant.get("funder", ""), grant.get("award_id", ""))
        if key not in seen:
            seen.add(key)
            result.append(grant)
    return result

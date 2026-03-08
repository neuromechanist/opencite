"""Shared utilities for opencite."""

from __future__ import annotations

import re
import unicodedata

from opencite.models import Author, Paper


def normalize_title(title: str) -> set[str]:
    """Normalize a title to a set of significant words for fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", title).lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return {w for w in normalized.split() if len(w) >= 3}


def titles_similar(t1: set[str], t2: set[str], threshold: float = 0.7) -> bool:
    """Check if two title word sets are similar using Jaccard similarity."""
    if not t1 or not t2:
        return False
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    return (intersection / union) >= threshold if union > 0 else False


def parse_author_name(name: str) -> Author:
    """Parse a name string into an Author, splitting family/given names.

    Handles formats:
        "Smith, Jane"    -> family=Smith, given=Jane
        "Jane Smith"     -> family=Smith, given=Jane
        "Smith"          -> family=Smith, given=""
    """
    name = name.strip()
    if not name:
        return Author(name="Unknown")

    if "," in name:
        parts = name.split(",", 1)
        family = parts[0].strip()
        given = parts[1].strip() if len(parts) > 1 else ""
    else:
        parts = name.rsplit(None, 1)
        if len(parts) == 2:
            given = parts[0].strip()
            family = parts[1].strip()
        else:
            family = parts[0].strip()
            given = ""

    return Author(name=name, family_name=family, given_name=given)


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """Reconstruct plaintext abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    max_pos = 0
    for positions in inverted_index.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(w for w in words if w)


def make_paper_filename(paper: Paper | None, identifier: str) -> str:
    """Generate a filename stem from paper metadata or identifier."""
    if paper and paper.title:
        author = ""
        if paper.authors:
            a = paper.authors[0]
            author = a.family_name or a.name.split(",")[0].strip()
            author = re.sub(r"[^\w]", "", author)

        year = paper.year_str
        words = paper.title.split()[:3]
        title_part = "_".join(re.sub(r"[^\w]", "", w) for w in words)
        parts = [p for p in [author, year, title_part] if p]
        return "_".join(parts)

    safe = re.sub(r"[^\w.-]", "_", identifier)
    return safe

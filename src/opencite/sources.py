"""Canonical source-name handling for `config.disabled_sources`.

A small helper that lets `disabled_sources` accept user-friendly aliases
("semantic-scholar", "semanticscholar") in addition to the canonical
short keys used by the orchestrator ("s2", "openalex", "pubmed", ...).
Kept independent of any client module to avoid circular imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Map any input alias -> canonical source key. Lookups normalize case and
# treat '-'/'_' as interchangeable so users don't have to memorize the
# exact spelling.
_ALIASES: dict[str, str] = {
    "openalex": "openalex",
    "s2": "s2",
    "semanticscholar": "s2",
    "semantic_scholar": "s2",
    "pubmed": "pubmed",
    "ncbi": "pubmed",
    "arxiv": "arxiv",
    "biorxiv": "biorxiv",
    "medrxiv": "medrxiv",
    "osf": "osf",
    "zenodo": "zenodo",
    "figshare": "figshare",
    "crossref": "crossref",
    "core": "core",
}


def canonicalize(name: str) -> str:
    """Return the canonical source key for an input alias.

    Unknown names pass through (lowercased) so a typo doesn't silently
    disable nothing; the caller can then log/warn if needed.
    """
    normalized = name.strip().lower().replace("-", "_")
    return _ALIASES.get(normalized, normalized)


def is_source_enabled(name: str, disabled: Iterable[str]) -> bool:
    """True when `name` is not present in `disabled` (after canonicalization)."""
    canon = canonicalize(name)
    disabled_canon = {canonicalize(d) for d in disabled}
    return canon not in disabled_canon

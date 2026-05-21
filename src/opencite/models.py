"""Data models for opencite."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class IDType(Enum):
    """Identifier types for academic papers."""

    DOI = "doi"
    PMID = "pmid"
    PMCID = "pmcid"
    OPENALEX = "openalex"
    S2 = "s2"
    ARXIV = "arxiv"


@dataclass(frozen=True)
class IDSet:
    """All known identifiers for a single paper.

    Immutable so it can be used for dedup lookups.
    """

    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    openalex_id: str = ""
    s2_id: str = ""
    arxiv_id: str = ""

    def has_any(self) -> bool:
        return bool(
            self.doi
            or self.pmid
            or self.pmcid
            or self.openalex_id
            or self.s2_id
            or self.arxiv_id
        )

    def best_lookup_id(self) -> tuple[IDType, str]:
        """Return the most useful ID for cross-API lookup.

        Priority: DOI > PMID > PMCID > S2 > OpenAlex > ArXiv.
        """
        if self.doi:
            return (IDType.DOI, self.doi)
        if self.pmid:
            return (IDType.PMID, self.pmid)
        if self.pmcid:
            return (IDType.PMCID, self.pmcid)
        if self.s2_id:
            return (IDType.S2, self.s2_id)
        if self.openalex_id:
            return (IDType.OPENALEX, self.openalex_id)
        if self.arxiv_id:
            return (IDType.ARXIV, self.arxiv_id)
        raise ValueError("No identifier available")

    def merge(self, other: IDSet) -> IDSet:
        """Create a new IDSet with the union of both sets' identifiers."""
        return IDSet(
            doi=self.doi or other.doi,
            pmid=self.pmid or other.pmid,
            pmcid=self.pmcid or other.pmcid,
            openalex_id=self.openalex_id or other.openalex_id,
            s2_id=self.s2_id or other.s2_id,
            arxiv_id=self.arxiv_id or other.arxiv_id,
        )


@dataclass
class Author:
    """Structured author representation."""

    name: str
    family_name: str = ""
    given_name: str = ""
    orcid: str = ""
    openalex_id: str = ""
    s2_id: str = ""

    def citation_name(self) -> str:
        """Format for citation: 'Smith, J.'"""
        if self.family_name and self.given_name:
            return f"{self.family_name}, {self.given_name[0]}."
        return self.name


@dataclass
class Source:
    """Journal or venue information."""

    name: str
    issn: str = ""
    publisher: str = ""
    is_oa: bool = False
    openalex_id: str = ""


@dataclass
class PDFLocation:
    """A known location where a PDF can be retrieved."""

    url: str
    source: str  # "openalex", "s2", "pmc", "doi"
    version: str = ""  # "publishedVersion", "acceptedVersion", "submittedVersion"
    is_oa: bool = False
    license: str = ""


@dataclass
class Paper:
    """Central data model for an academic paper.

    Designed to be populated incrementally: a search fills basic fields,
    then enrichment passes add TLDR, PDF locations, etc.
    """

    # Identity
    title: str
    ids: IDSet = field(default_factory=IDSet)

    # Authorship
    authors: list[Author] = field(default_factory=list)

    # Publication
    year: int | None = None
    source_venue: Source | None = None
    publication_date: str = ""
    pub_type: str = ""

    # Content
    abstract: str = ""
    tldr: str = ""
    keywords: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    # Metrics
    citation_count: int = 0
    influential_citation_count: int = 0
    is_retracted: bool = False

    # Access
    url: str = ""
    pdf_locations: list[PDFLocation] = field(default_factory=list)
    is_oa: bool = False
    # OpenAlex-style enum: "gold", "hybrid", "green", "bronze", "closed",
    # "diamond", or "" when unknown. `is_oa = True` collapses gold/hybrid/
    # green/bronze together, but the redistribution implications differ
    # (e.g. bronze is free-to-read but not openly licensed). Consumers
    # publishing artifacts based on PDFs we retrieve should consult this
    # field rather than `is_oa` alone. opencite reports `oa_status` but
    # does not filter on it -- the publication-vs-redistribution decision
    # belongs to the caller.
    oa_status: str = ""

    # Provenance
    data_sources: set[str] = field(default_factory=set)

    # Grants
    grants: list[dict[str, str]] = field(default_factory=list)

    # Cached BibTeX
    _bibtex: str = field(default="", repr=False)

    @property
    def doi(self) -> str:
        return self.ids.doi

    @property
    def pmid(self) -> str:
        return self.ids.pmid

    @property
    def pmcid(self) -> str:
        return self.ids.pmcid

    @property
    def journal(self) -> str:
        return self.source_venue.name if self.source_venue else ""

    @property
    def authors_short(self) -> str:
        """'Smith et al.' format."""
        if not self.authors:
            return "Unknown"
        first = self.authors[0].family_name or self.authors[0].name
        if len(self.authors) == 1:
            return first
        if len(self.authors) == 2:
            second = self.authors[1].family_name or self.authors[1].name
            return f"{first} & {second}"
        return f"{first} et al."

    @property
    def best_pdf_url(self) -> str | None:
        """Return the best available PDF URL."""
        if not self.pdf_locations:
            return None
        for loc in self.pdf_locations:
            if loc.version == "publishedVersion":
                return loc.url
        return self.pdf_locations[0].url

    @property
    def year_str(self) -> str:
        return str(self.year) if self.year else ""


@dataclass
class SearchResult:
    """Result of a multi-source search."""

    query: str
    papers: list[Paper]
    total_by_source: dict[str, int] = field(default_factory=dict)
    deduplicated_count: int = 0


@dataclass
class CitationResult:
    """Result of a citation graph query."""

    seed_paper: Paper
    papers: list[Paper]
    direction: str  # "citing" or "references"
    total_available: int = 0


def parse_identifier(raw: str) -> tuple[IDType, str]:
    """Auto-detect identifier type from a raw string.

    Formats:
        10.xxx/yyy              -> DOI
        pmid:12345              -> PMID
        pmc:PMC12345            -> PMCID
        PMC12345                -> PMCID
        arxiv:2106.15928        -> ArXiv
        2106.15928[vN]          -> ArXiv (bare new-style ID)
        cs.LG/0101001           -> ArXiv (bare old-style ID)
        https://arxiv.org/abs/… -> ArXiv (URL)
        https://arxiv.org/pdf/… -> ArXiv (URL)
        https://www.biorxiv.org/content/… -> DOI extracted from URL
        https://www.medrxiv.org/content/… -> DOI extracted from URL
        W1234567890             -> OpenAlex
        40-char hex             -> S2 paper ID
    """
    s = raw.strip()

    # --- arXiv / bioRxiv URL detection (must come before DOI pattern) ---

    # arXiv URLs: https://arxiv.org/abs/2106.15928[v2]
    #             https://arxiv.org/pdf/2106.15928[v2]
    #             https://arxiv.org/html/2106.15928[v2]
    arxiv_url_match = re.match(
        r"https?://(?:ar[xX]iv\.org|export\.arxiv\.org)/(?:abs|pdf|html|e-print)/"
        r"([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-zA-Z.-]+/\d+(?:v\d+)?)",
        s,
    )
    if arxiv_url_match:
        arxiv_id = arxiv_url_match.group(1)
        # Strip version suffix for canonical ID
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        return (IDType.ARXIV, arxiv_id)

    # bioRxiv/medRxiv URLs: extract DOI from URL path
    # e.g. https://www.biorxiv.org/content/10.1101/2021.01.01.425001v2
    biorxiv_url_match = re.match(
        r"https?://www\.(?:bio|med)rxiv\.org/content/(10\.\d{4,}/\S+?)(?:v\d+)?(?:\.full(?:\.pdf)?)?$",
        s,
    )
    if biorxiv_url_match:
        return (IDType.DOI, biorxiv_url_match.group(1))

    # --- Explicit prefixes ---
    lower = s.lower()
    if lower.startswith("pmid:"):
        return (IDType.PMID, s[5:])
    if lower.startswith("pmc:"):
        val = s[4:]
        if not val.upper().startswith("PMC"):
            val = f"PMC{val}"
        return (IDType.PMCID, val)
    if lower.startswith("arxiv:"):
        # Strip optional version: arXiv:2106.15928v2 -> 2106.15928
        arxiv_id = re.sub(r"v\d+$", "", s[6:])
        return (IDType.ARXIV, arxiv_id)
    if lower.startswith("doi:"):
        return (IDType.DOI, s[4:])

    # --- PMC ID without prefix ---
    if s.upper().startswith("PMC") and s[3:].isdigit():
        return (IDType.PMCID, s.upper())

    # --- DOI pattern ---
    if re.match(r"^10\.\d{4,}/", s):
        return (IDType.DOI, s)

    # --- OpenAlex ID ---
    if re.match(r"^W\d+$", s):
        return (IDType.OPENALEX, s)

    # --- S2 40-char hex ---
    if re.match(r"^[0-9a-f]{40}$", s):
        return (IDType.S2, s)

    # --- Bare arXiv ID (new format): YYMM.NNNNN[vN] ---
    # Must be checked before bare-digits fallback
    if re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", s):
        arxiv_id = re.sub(r"v\d+$", "", s)
        return (IDType.ARXIV, arxiv_id)

    # --- Bare arXiv ID (old format): area.subarea/YYMMNNN[vN] ---
    if re.match(r"^[a-zA-Z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?$", s):
        arxiv_id = re.sub(r"v\d+$", "", s)
        return (IDType.ARXIV, arxiv_id)

    # --- Bare digits -> assume PMID ---
    if s.isdigit():
        return (IDType.PMID, s)

    raise ValueError(f"Cannot determine identifier type for: {raw}")

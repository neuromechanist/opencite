"""Semantic Scholar API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"

# Fields to request for full paper metadata
PAPER_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "abstract",
        "year",
        "url",
        "openAccessPdf",
        "citationCount",
        "influentialCitationCount",
        "externalIds",
        "authors",
        "journal",
        "tldr",
        "citationStyles",
        "s2FieldsOfStudy",
        "publicationTypes",
        "isOpenAccess",
        "publicationDate",
    ]
)

# Lighter fields for citation/reference lists
CITATION_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "abstract",
        "year",
        "url",
        "openAccessPdf",
        "citationCount",
        "influentialCitationCount",
        "externalIds",
        "authors",
        "journal",
        "isOpenAccess",
    ]
)


class SemanticScholarClient(BaseClient):
    """Client for the Semantic Scholar Academic Graph API.

    Uses a process-wide shared rate limiter (`shared_limiter_key = "s2"`)
    because S2's free tier caps the entire account at ~1 req/sec even with
    an API key; multiple parallel `SemanticScholarClient` instances would
    otherwise multiply requests and trigger 429s.
    """

    shared_limiter_key: ClassVar[str | None] = "s2"

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.s2_rate_limit,
            burst=1,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.semantic_scholar_api_key:
            headers["x-api-key"] = self.config.semantic_scholar_api_key
        return headers

    async def search(
        self,
        query: str,
        max_results: int = 20,
        fields: str | None = None,
    ) -> list[Paper]:
        """Search for papers by keyword query."""
        params: dict[str, Any] = {
            "query": query,
            "limit": min(max_results, 100),
            "fields": fields or PAPER_FIELDS,
        }
        resp = await self.get("/paper/search", params=params)
        data = resp.json()
        return [self._parse_paper(p) for p in data.get("data", []) if p.get("title")]

    async def lookup(self, paper_id: str, fields: str | None = None) -> Paper | None:
        """Look up a single paper by ID.

        Accepts formats: DOI:X, PMID:X, ARXIV:X, PMCID:X, CorpusId:X,
        or a raw S2 paper ID (40-char hex).
        """
        try:
            resp = await self.get(
                f"/paper/{paper_id}",
                params={"fields": fields or PAPER_FIELDS},
            )
            return self._parse_paper(resp.json())
        except Exception:
            logger.debug("S2 lookup failed for %s", paper_id)
            return None

    async def batch_lookup(
        self,
        paper_ids: list[str],
        fields: str | None = None,
    ) -> list[Paper]:
        """Batch lookup up to 500 papers via POST /paper/batch."""
        papers: list[Paper] = []
        # Process in chunks of 500
        for i in range(0, len(paper_ids), 500):
            chunk = paper_ids[i : i + 500]
            try:
                resp = await self.post(
                    "/paper/batch",
                    params={"fields": fields or PAPER_FIELDS},
                    json={"ids": chunk},
                )
                for p in resp.json():
                    if p and p.get("title"):
                        papers.append(self._parse_paper(p))
            except Exception:
                logger.warning("S2 batch lookup failed for chunk starting at %d", i)
        return papers

    async def citing_papers(
        self,
        paper_id: str,
        max_results: int = 50,
        fields: str | None = None,
    ) -> list[Paper]:
        """Get papers that cite the given paper."""
        params: dict[str, Any] = {
            "fields": fields or CITATION_FIELDS,
            "limit": min(max_results, 1000),
        }
        resp = await self.get(f"/paper/{paper_id}/citations", params=params)
        data = resp.json()
        papers = []
        for item in data.get("data", []):
            citing = item.get("citingPaper", {})
            if citing.get("title"):
                papers.append(self._parse_paper(citing))
        return papers

    async def references(
        self,
        paper_id: str,
        max_results: int = 50,
        fields: str | None = None,
    ) -> list[Paper]:
        """Get papers referenced by the given paper."""
        params: dict[str, Any] = {
            "fields": fields or CITATION_FIELDS,
            "limit": min(max_results, 1000),
        }
        resp = await self.get(f"/paper/{paper_id}/references", params=params)
        data = resp.json()
        papers = []
        for item in data.get("data", []):
            ref = item.get("citedPaper", {})
            if ref.get("title"):
                papers.append(self._parse_paper(ref))
        return papers

    def _parse_paper(self, data: dict) -> Paper:
        """Parse an S2 paper JSON object into a Paper model."""
        ext_ids = data.get("externalIds") or {}

        ids = IDSet(
            doi=ext_ids.get("DOI", ""),
            pmid=ext_ids.get("PubMed", ""),
            pmcid=ext_ids.get("PubMedCentral", ""),
            s2_id=data.get("paperId", ""),
            arxiv_id=ext_ids.get("ArXiv", ""),
        )

        # Authors
        authors = []
        for a in (data.get("authors") or [])[:50]:
            name = a.get("name", "")
            if not name:
                continue
            parts = name.rsplit(None, 1)
            family = parts[-1] if parts else name
            given = parts[0] if len(parts) > 1 else ""
            authors.append(
                Author(
                    name=name,
                    family_name=family,
                    given_name=given,
                    s2_id=a.get("authorId", ""),
                )
            )

        # Journal
        journal_info = data.get("journal") or {}
        source_venue = None
        journal_name = journal_info.get("name", "")
        if journal_name:
            source_venue = Source(name=journal_name)

        # PDF
        pdf_locations = []
        oa_pdf = data.get("openAccessPdf")
        if oa_pdf and oa_pdf.get("url"):
            pdf_locations.append(
                PDFLocation(
                    url=oa_pdf["url"],
                    source="s2",
                    is_oa=True,
                )
            )

        # TLDR
        tldr_obj = data.get("tldr")
        tldr = tldr_obj.get("text", "") if tldr_obj else ""

        # Fields of study
        topics = []
        for f in data.get("s2FieldsOfStudy") or []:
            cat = f.get("category", "")
            if cat:
                topics.append(cat)

        # Publication types
        pub_types = data.get("publicationTypes") or []
        pub_type = pub_types[0] if pub_types else ""

        # BibTeX from citationStyles
        bibtex = ""
        citation_styles = data.get("citationStyles")
        if citation_styles and isinstance(citation_styles, dict):
            bibtex = citation_styles.get("bibtex", "")

        return Paper(
            title=data.get("title", ""),
            ids=ids,
            authors=authors,
            year=data.get("year"),
            source_venue=source_venue,
            publication_date=data.get("publicationDate") or "",
            pub_type=pub_type,
            abstract=(data.get("abstract") or "")[:1000],
            tldr=tldr,
            topics=topics,
            citation_count=data.get("citationCount", 0) or 0,
            influential_citation_count=data.get("influentialCitationCount", 0) or 0,
            url=data.get("url", ""),
            pdf_locations=pdf_locations,
            is_oa=data.get("isOpenAccess", False) or False,
            data_sources={"s2"},
            _bibtex=bibtex,
        )

"""arXiv API client (Atom v1)."""

from __future__ import annotations

import contextlib
import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://export.arxiv.org/api"

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"

# arXiv asks for at most 1 req/3 sec without an API key;
# 3 req/sec is the absolute max for bulk access
_DEFAULT_RATE = 3.0


class ArXivClient(BaseClient):
    """Client for the arXiv Atom v1 search API.

    Requires no API key. arXiv's terms of service ask for polite
    crawling (<= 1 req/3 sec for bulk; 3/sec is the hard cap).
    """

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.arxiv_rate_limit,
            burst=1,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.contact_email:
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        return headers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[Paper]:
        """Search arXiv for papers matching *query*.

        Uses ``all:`` field so the query matches title, abstract, and authors.
        """
        # Build arXiv query
        # arXiv query syntax uses field prefixes; fall back to `all:`
        search_query = f"all:{query}"
        params: dict[str, Any] = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max_results, 200),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        resp = await self.get("/query", params=params)
        return self._parse_feed(resp.text, year_from=year_from, year_to=year_to)

    async def lookup_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Look up a single paper by arXiv ID (e.g. ``2106.15928`` or ``cs.LG/0101001``)."""
        clean_id = arxiv_id.strip()
        # Strip version suffix for the API call (arXiv returns latest by default)
        bare_id = clean_id.split("v")[0] if "v" in clean_id.lower() else clean_id
        try:
            resp = await self.get("/query", params={"id_list": bare_id})
            papers = self._parse_feed(resp.text)
            return papers[0] if papers else None
        except Exception:
            logger.debug("arXiv lookup failed for %s", arxiv_id)
            return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_feed(
        self,
        xml_text: str,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[Paper]:
        """Parse an Atom feed response into a list of Papers."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("arXiv: failed to parse Atom XML")
            return []

        papers: list[Paper] = []
        for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
            paper = self._parse_entry(entry)
            if paper is None:
                continue
            if year_from and paper.year and paper.year < year_from:
                continue
            if year_to and paper.year and paper.year > year_to:
                continue
            papers.append(paper)
        return papers

    def _parse_entry(self, entry: ET.Element) -> Paper | None:
        """Parse a single Atom entry into a Paper."""

        def _text(tag: str, ns: str = _ATOM_NS) -> str:
            el = entry.find(f"{{{ns}}}{tag}")
            return (el.text or "").strip() if el is not None else ""

        title = _text("title").replace("\n", " ").strip()
        if not title:
            return None

        # arXiv ID lives in <id> as a URL:
        # http://arxiv.org/abs/2106.15928v1  (old style, still common)
        # https://arxiv.org/abs/2106.15928v1
        raw_id = _text("id")
        arxiv_id = ""
        if raw_id:
            m = re.search(
                r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}|[a-zA-Z.-]+/\d+)",
                raw_id,
            )
            if m:
                arxiv_id = m.group(1)

        # DOI (may be empty for pure preprints)
        doi = _text("doi", ns=_ARXIV_NS)

        ids = IDSet(doi=doi, arxiv_id=arxiv_id)

        # Published / updated dates
        published = _text("published")  # e.g. "2021-06-30T00:00:00Z"
        year: int | None = None
        pub_date = ""
        if published:
            pub_date = published[:10]  # "YYYY-MM-DD"
            with contextlib.suppress(ValueError):
                year = int(published[:4])

        # Authors
        authors: list[Author] = []
        for author_el in entry.findall(f"{{{_ATOM_NS}}}author"):
            name_el = author_el.find(f"{{{_ATOM_NS}}}name")
            if name_el is None or not name_el.text:
                continue
            name = name_el.text.strip()
            parts = name.rsplit(None, 1)
            family = parts[-1] if parts else name
            given = parts[0] if len(parts) > 1 else ""
            authors.append(Author(name=name, family_name=family, given_name=given))

        # Abstract
        abstract = _text("summary").replace("\n", " ").strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        # arXiv categories as topics
        topics: list[str] = []
        for cat_el in entry.findall(f"{{{_ATOM_NS}}}category"):
            term = cat_el.get("term", "")
            if term:
                topics.append(term)

        # Primary category as source/journal
        primary_cat = ""
        prim_el = entry.find(f"{{{_ARXIV_NS}}}primary_category")
        if prim_el is not None:
            primary_cat = prim_el.get("term", "")

        source_venue: Source | None = None
        if primary_cat:
            source_venue = Source(name=f"arXiv:{primary_cat}", is_oa=True)

        # PDF URL: arXiv always provides it at /pdf/{arxiv_id}
        pdf_locations: list[PDFLocation] = []
        if arxiv_id:
            pdf_locations.append(
                PDFLocation(
                    url=f"https://arxiv.org/pdf/{arxiv_id}",
                    version="submittedVersion",
                    is_oa=True,
                    source="arxiv",
                )
            )

        # HTML URL
        url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else raw_id

        # Journal ref (if published)
        journal_ref = _text("journal_ref", ns=_ARXIV_NS)
        if journal_ref and source_venue:
            source_venue = Source(
                name=journal_ref,
                is_oa=source_venue.is_oa,
            )
        elif journal_ref:
            source_venue = Source(name=journal_ref)

        return Paper(
            title=title,
            ids=ids,
            authors=authors,
            year=year,
            source_venue=source_venue,
            publication_date=pub_date,
            pub_type="preprint",
            abstract=abstract,
            topics=topics,
            is_oa=True,
            url=url,
            pdf_locations=pdf_locations,
            data_sources={"arxiv"},
        )

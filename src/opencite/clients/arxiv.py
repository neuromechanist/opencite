"""arXiv API client (Atom v1)."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from opencite.clients.preprint_base import (
    FulltextRoute,
    PreprintClient,
    html_to_markdown,
)
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://export.arxiv.org/api"
AR5IV_BASE = "https://ar5iv.labs.arxiv.org"

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"

# arXiv DOI prefix (Datacite-registered arXiv DOIs follow `10.48550/arXiv.<id>`).
_ARXIV_DOI_PREFIX = "10.48550/arxiv."


class ArXivClient(PreprintClient):
    """Client for the arXiv Atom v1 search API.

    Requires no API key. arXiv's terms of service ask for polite
    crawling (<= 1 req/3 sec for bulk; 3/sec is the hard cap).
    """

    name: ClassVar[str] = "arxiv"

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
        **_kwargs: object,
    ) -> list[Paper]:
        """Search arXiv for papers matching *query*.

        Uses ``all:`` field so the query matches title, abstract, and authors.
        """
        params: dict[str, Any] = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(max_results, 200),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        try:
            resp = await self.get("/query", params=params)
        except APIError as e:
            logger.warning("arXiv search failed for query %r: %s", query, e.message)
            return []
        return self._parse_feed(resp.text, year_from=year_from, year_to=year_to)

    async def lookup_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Look up a single paper by arXiv ID (e.g. ``2106.15928`` or ``cs.LG/0101001``)."""
        # Use regex to strip version suffix so old-style IDs like
        # "solv-int/9901001" are not corrupted by a naive split("v").
        bare_id = re.sub(r"v\d+$", "", arxiv_id.strip())
        try:
            resp = await self.get("/query", params={"id_list": bare_id})
            papers = self._parse_feed(resp.text)
            return papers[0] if papers else None
        except APIError as e:
            logger.warning("arXiv lookup failed for %s: %s", arxiv_id, e.message)
            return None

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up an arXiv preprint by DOI.

        arXiv DOIs follow ``10.48550/arXiv.<id>`` (Datacite). For other DOIs
        (e.g. publisher DOIs assigned after journal acceptance) this returns
        None; the orchestrator falls back to other clients.
        """
        normalized = doi.strip().lower()
        if not normalized.startswith(_ARXIV_DOI_PREFIX):
            return None
        arxiv_id = doi.strip()[len(_ARXIV_DOI_PREFIX) :]
        return await self.lookup_arxiv_id(arxiv_id)

    # ------------------------------------------------------------------
    # Full-text retrieval (ar5iv HTML5)
    # ------------------------------------------------------------------

    def fulltext_route(self, paper: Paper) -> FulltextRoute:
        """Use ar5iv HTML when an arXiv ID can be derived from the paper."""
        return (
            FulltextRoute.HTML if self._derive_arxiv_id(paper) else FulltextRoute.NONE
        )

    async def fetch_fulltext(self, paper: Paper) -> str | None:
        """Fetch the ar5iv HTML5 rendering of *paper* and return markdown.

        ar5iv (https://ar5iv.labs.arxiv.org) renders LaTeX source as semantic
        HTML5, which converts to markdown more cleanly than the PDF and
        preserves equations as MathML. Returns None when the paper has no
        derivable arXiv ID, the response is not 200, or conversion fails.
        """
        arxiv_id = self._derive_arxiv_id(paper)
        if not arxiv_id:
            return None

        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        url = f"{AR5IV_BASE}/html/{arxiv_id}"
        try:
            await self.rate_limiter.acquire()
            resp = await self._client.get(url, follow_redirects=True)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning("ar5iv fetch failed for %s: %s", arxiv_id, e)
            return None

        if resp.status_code != 200:
            logger.warning("ar5iv returned HTTP %d for %s", resp.status_code, arxiv_id)
            return None

        return html_to_markdown(resp.text, context=f"arxiv:{arxiv_id}")

    @staticmethod
    def _derive_arxiv_id(paper: Paper) -> str:
        """Pull an arXiv ID out of `paper` via `ids.arxiv_id` or a Datacite DOI."""
        if paper.ids.arxiv_id:
            return paper.ids.arxiv_id.strip()
        doi = (paper.doi or "").strip()
        if doi.lower().startswith(_ARXIV_DOI_PREFIX):
            return doi[len(_ARXIV_DOI_PREFIX) :]
        return ""

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
        except ET.ParseError as exc:
            logger.warning(
                "arXiv: failed to parse Atom XML (%s). Preview: %.100r",
                exc,
                xml_text,
            )
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
            try:
                year = int(published[:4])
            except ValueError:
                logger.debug("arXiv: unexpected date format %r", published)

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

        # Journal ref (if published in a journal)
        journal_ref = _text("journal_ref", ns=_ARXIV_NS)
        if journal_ref and source_venue:
            source_venue = Source(name=journal_ref, is_oa=source_venue.is_oa)
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

"""bioRxiv / medRxiv client.

Uses two APIs:
1. bioRxiv Content API (https://api.biorxiv.org) -- authoritative metadata and
   DOI lookup for individual preprints.
2. CrossRef REST API (https://api.crossref.org) -- keyword search filtered to
   bioRxiv/medRxiv preprints, since the bioRxiv Content API has no free-text
   search endpoint.

No API key is required for either.  CrossRef's polite pool (which gives better
throughput) is activated by supplying a contact email via ``config.contact_email``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

_BIORXIV_BASE = "https://api.biorxiv.org"
_CROSSREF_BASE = "https://api.crossref.org"

# bioRxiv DOI prefix -- all biorxiv/medrxiv preprints share 10.1101
_BIORXIV_DOI_PREFIX = "10.1101/"

# CrossRef "type" for preprints
_PREPRINT_TYPE = "posted-content"


class BioRxivClient(BaseClient):
    """Client for bioRxiv and medRxiv preprint servers.

    Keyword search is routed through the CrossRef API (which indexes all
    bioRxiv/medRxiv DOIs).  Individual DOI lookups go to the bioRxiv Content
    API for authoritative metadata.
    """

    def __init__(self, config: Config) -> None:
        # Use bioRxiv Content API as the base URL; CrossRef calls use a
        # separate httpx session to avoid base-URL clashes.
        super().__init__(
            config=config,
            base_url=_BIORXIV_BASE,
            rate_limit=config.biorxiv_rate_limit,
            burst=5,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.contact_email:
            # CrossRef polite-pool header
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        return headers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 20,
        server: str = "biorxiv",
    ) -> list[Paper]:
        """Search bioRxiv/medRxiv via CrossRef.

        Args:
            query: Free-text query.
            max_results: Maximum number of results to return.
            server: ``"biorxiv"``, ``"medrxiv"``, or ``"both"``.
                    bioRxiv and medRxiv share the ``10.1101/`` DOI prefix;
                    when set to ``"both"`` (default behavior when caller
                    passes no preference) all preprints are returned.
        """
        papers: list[Paper] = []

        # All bioRxiv/medRxiv preprints use the 10.1101 DOI prefix.
        # CrossRef's "container-title" field is unreliable for preprints, so
        # we filter by prefix + type instead.
        # The `server` param is kept for API consistency and future use when
        # CrossRef improves preprint-server filtering.
        _ = server  # intentionally unused until CrossRef supports it reliably
        filter_parts = ["prefix:10.1101", f"type:{_PREPRINT_TYPE}"]

        params: dict[str, Any] = {
            "query.bibliographic": query,
            "filter": ",".join(filter_parts),
            "rows": min(max_results, 100),
            "select": (
                "DOI,title,author,published,created,abstract,"
                "container-title,URL,is-referenced-by-count"
            ),
        }
        if self.config.contact_email:
            params["mailto"] = self.config.contact_email

        try:
            import httpx

            async with httpx.AsyncClient(
                base_url=_CROSSREF_BASE,
                timeout=self.timeout,
                headers=self._default_headers(),
            ) as client:
                resp = await client.get("/works", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.warning("BioRxiv CrossRef search failed for query: %s", query)
            return []

        for item in (data.get("message") or {}).get("items") or []:
            paper = self._parse_crossref_item(item)
            if paper:
                papers.append(paper)
        return papers

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a single preprint by DOI using the bioRxiv Content API.

        Tries bioRxiv first, then medRxiv (both share the ``10.1101/`` prefix).
        """
        for server in ("biorxiv", "medrxiv"):
            try:
                resp = await self.get(f"/details/{server}/{doi}")
                data = resp.json()
            except Exception:
                logger.debug("BioRxiv content API failed for %s on %s", doi, server)
                continue

            collection = data.get("collection") or []
            if not collection:
                continue

            # Use the latest version (last entry)
            entry = collection[-1]
            return self._parse_content_entry(entry, server=server)

        logger.debug("BioRxiv: no results for DOI %s on either server", doi)
        return None

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_content_entry(
        self, entry: dict, server: str = "biorxiv"
    ) -> Paper | None:
        """Parse a single record from the bioRxiv Content API."""
        doi = (entry.get("doi") or "").strip()
        title = (entry.get("title") or "").strip()
        if not title:
            return None

        # Version
        version = str(entry.get("version") or "1")

        arxiv_id = ""
        ids = IDSet(doi=doi, arxiv_id=arxiv_id)

        # Date
        date_str = (entry.get("date") or "")[:10]  # "YYYY-MM-DD"
        year: int | None = None
        if date_str and date_str[:4].isdigit():
            year = int(date_str[:4])

        # Authors  -- stored as "Smith J, Jones AB, ..."
        raw_authors = entry.get("authors") or ""
        authors: list[Author] = []
        if raw_authors:
            for raw in str(raw_authors).split(";"):
                name = raw.strip()
                if not name:
                    continue
                # Typical format: "Smith J" or "Smith Jane"
                parts = name.split()
                family = parts[0] if parts else name
                given = " ".join(parts[1:]) if len(parts) > 1 else ""
                authors.append(Author(name=name, family_name=family, given_name=given))

        abstract = (entry.get("abstract") or "").strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        # Category
        category = (entry.get("category") or "").strip()
        topics = [category] if category else []
        source_venue = Source(
            name=server.capitalize(),
            is_oa=True,
        )

        # Direct PDF URL: bioRxiv always provides versioned PDFs
        pdf_locations: list[PDFLocation] = []
        if doi:
            pdf_url = f"https://www.{server}.org/content/{doi}v{version}.full.pdf"
            pdf_locations.append(
                PDFLocation(
                    url=pdf_url,
                    version="submittedVersion",
                    is_oa=True,
                    source=server,
                )
            )

        url = f"https://www.{server}.org/content/{doi}v{version}" if doi else ""

        return Paper(
            title=title,
            ids=ids,
            authors=authors,
            year=year,
            source_venue=source_venue,
            publication_date=date_str,
            pub_type="preprint",
            abstract=abstract,
            topics=topics,
            is_oa=True,
            url=url,
            pdf_locations=pdf_locations,
            data_sources={server},
        )

    def _parse_crossref_item(self, item: dict) -> Paper | None:
        """Parse a CrossRef works item into a Paper."""
        doi = (item.get("DOI") or "").strip()
        titles = item.get("title") or []
        title = titles[0].strip() if titles else ""
        if not title:
            return None

        ids = IDSet(doi=doi)

        # Date
        published = item.get("published") or item.get("created") or {}
        date_parts = (published.get("date-parts") or [[]])[0]
        year: int | None = int(date_parts[0]) if date_parts else None
        pub_date = (
            "-".join(str(p).zfill(2) for p in date_parts)
            if len(date_parts) >= 3
            else (str(date_parts[0]) if date_parts else "")
        )

        # Authors
        authors: list[Author] = []
        for a in item.get("author") or []:
            family = (a.get("family") or "").strip()
            given = (a.get("given") or "").strip()
            name = f"{given} {family}".strip() if given else family
            if not name:
                continue
            authors.append(Author(name=name, family_name=family, given_name=given))

        abstract = (item.get("abstract") or "").strip()
        # CrossRef wraps abstracts in JATS XML tags
        if "<" in abstract:
            import re

            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        container = item.get("container-title") or []
        server_name = container[0].lower() if container else "biorxiv"
        source_venue = Source(name=server_name.capitalize(), is_oa=True)

        # PDF URL from DOI
        pdf_locations: list[PDFLocation] = []
        if doi:
            server = "medrxiv" if "medrxiv" in server_name else "biorxiv"
            pdf_url = f"https://www.{server}.org/content/{doi}v1.full.pdf"
            pdf_locations.append(
                PDFLocation(
                    url=pdf_url,
                    version="submittedVersion",
                    is_oa=True,
                    source=server,
                )
            )

        url = (item.get("URL") or f"https://doi.org/{doi}") if doi else ""

        citation_count = item.get("is-referenced-by-count") or 0

        return Paper(
            title=title,
            ids=ids,
            authors=authors,
            year=year,
            source_venue=source_venue,
            publication_date=pub_date,
            pub_type="preprint",
            abstract=abstract,
            is_oa=True,
            url=url,
            pdf_locations=pdf_locations,
            citation_count=citation_count,
            data_sources={"biorxiv"},
        )

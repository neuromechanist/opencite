"""CrossRef REST API client.

CrossRef (https://api.crossref.org) is the authoritative DOI metadata
registry with 150M+ works.  No API key required; providing a contact
email activates the "polite" pool with better throughput.

This client provides:
- DOI metadata lookup (filling gaps when S2/OpenAlex miss a DOI)
- Keyword search across all registered works
- PDF link extraction from CrossRef ``link`` records
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org"


class CrossRefClient(BaseClient):
    """Client for the CrossRef REST API.

    Provides broad DOI-based metadata coverage and keyword search
    for works not indexed by the existing five sources.
    """

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.crossref_rate_limit,
            burst=10,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.contact_email:
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        return headers

    async def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[Paper]:
        """Search CrossRef works by keyword query."""
        params: dict[str, Any] = {
            "query": query,
            "rows": min(max_results, 100),
            "select": (
                "DOI,title,author,published-print,published-online,"
                "container-title,type,abstract,is-referenced-by-count,"
                "link,ISSN,publisher"
            ),
        }

        filters: list[str] = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}")
        if year_to:
            filters.append(f"until-pub-date:{year_to}")
        if filters:
            params["filter"] = ",".join(filters)

        try:
            resp = await self.get("/works", params=params)
            data = resp.json()
        except Exception as e:
            logger.warning("CrossRef search failed: %s", e)
            return []

        items = data.get("message", {}).get("items", [])
        return [p for item in items if (p := _parse_work(item)) is not None]

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a single work by DOI."""
        try:
            resp = await self.get(f"/works/{doi}")
            data = resp.json()
        except Exception as e:
            logger.debug("CrossRef lookup failed for %s: %s", doi, e)
            return None

        work = data.get("message", {})
        return _parse_work(work)


def _parse_work(work: dict[str, Any]) -> Paper | None:
    """Parse a CrossRef work item into a Paper."""
    title_list = work.get("title", [])
    if not title_list:
        return None
    title = title_list[0]

    doi = work.get("DOI", "")

    # Extract year from published-print or published-online
    year = None
    for date_field in ("published-print", "published-online"):
        parts = work.get(date_field, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            with contextlib.suppress(TypeError, ValueError):
                year = int(parts[0][0])
            break

    # Publication date string
    pub_date = ""
    for date_field in ("published-print", "published-online"):
        parts = work.get(date_field, {}).get("date-parts", [[]])
        if parts and parts[0]:
            pub_date = "-".join(str(p) for p in parts[0] if p)
            break

    # Authors
    authors = []
    for auth in work.get("author", [])[:50]:
        family = auth.get("family", "")
        given = auth.get("given", "")
        name = f"{given} {family}".strip() if given and family else family or given
        if name:
            authors.append(
                Author(
                    name=name,
                    family_name=family,
                    given_name=given,
                    orcid=auth.get("ORCID", "") or "",
                )
            )

    # Source/venue
    container = work.get("container-title", [])
    venue_name = container[0] if container else ""
    issn_list = work.get("ISSN", [])
    source_venue = (
        Source(
            name=venue_name,
            issn=issn_list[0] if issn_list else "",
            publisher=work.get("publisher", ""),
        )
        if venue_name
        else None
    )

    # Abstract (CrossRef provides JATS XML; strip tags)
    abstract = work.get("abstract", "")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()[:1000]

    # PDF locations from link records
    pdf_locations = []
    for link in work.get("link", []):
        if link.get("content-type") == "application/pdf":
            url = link.get("URL", "")
            if url:
                pdf_locations.append(
                    PDFLocation(
                        url=url,
                        source="crossref",
                        version="publishedVersion",
                        is_oa=False,
                    )
                )

    citation_count = work.get("is-referenced-by-count", 0) or 0

    return Paper(
        title=title,
        ids=IDSet(doi=doi),
        authors=authors,
        year=year,
        source_venue=source_venue,
        publication_date=pub_date,
        pub_type=work.get("type", ""),
        abstract=abstract,
        citation_count=citation_count,
        pdf_locations=pdf_locations,
        data_sources={"crossref"},
    )

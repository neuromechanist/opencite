"""CORE API client.

CORE (https://core.ac.uk) aggregates open access research from thousands
of repositories and journals worldwide -- the world's largest collection
of OA full texts (300M+ metadata records, 40M+ full texts).

Requires a free API key from https://core.ac.uk/services/api.
The free tier allows 1 batch request or 5 single requests per 10 seconds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.core.ac.uk"


class COREClient(BaseClient):
    """Client for the CORE API v3.

    Provides keyword search and DOI lookup for open access papers,
    including full-text download URLs.
    """

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=0.5,  # 5 req per 10 seconds
            burst=2,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        api_key = self.config.core_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @property
    def _enabled(self) -> bool:
        return bool(self.config.core_api_key)

    async def search(self, query: str, max_results: int = 20) -> list[Paper]:
        """Search CORE for open access papers."""
        if not self._enabled:
            logger.debug("CORE API key not set; skipping search")
            return []

        params: dict[str, Any] = {
            "q": query,
            "limit": min(max_results, 100),
        }

        try:
            resp = await self.get("/v3/search/works", params=params)
        except Exception as e:
            logger.warning("CORE search failed: %s", e)
            return []

        data = resp.json()
        results = data.get("results", [])
        return [p for item in results if (p := _parse_work(item)) is not None]

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a paper by DOI in CORE."""
        if not self._enabled:
            return None

        try:
            resp = await self.get(
                "/v3/search/works", params={"q": f'doi:"{doi}"', "limit": 1}
            )
        except Exception as e:
            logger.debug("CORE lookup failed for %s: %s", doi, e)
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        return _parse_work(results[0])


def _parse_work(work: dict[str, Any]) -> Paper | None:
    """Parse a CORE work/output into a Paper."""
    title = work.get("title", "")
    if not title:
        return None

    doi = work.get("doi") or ""
    # CORE sometimes prefixes DOIs with https://doi.org/
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/") :]
    elif doi.startswith("http://doi.org/"):
        doi = doi[len("http://doi.org/") :]

    year = work.get("yearPublished")

    # Authors
    authors = []
    for auth_name in work.get("authors", [])[:50]:
        if isinstance(auth_name, str) and auth_name:
            authors.append(Author(name=auth_name))
        elif isinstance(auth_name, dict):
            name = auth_name.get("name", "")
            if name:
                authors.append(Author(name=name))

    # Venue
    journal = work.get("journals", [])
    venue_name = ""
    if journal and isinstance(journal[0], dict):
        venue_name = journal[0].get("title", "")
    elif journal and isinstance(journal[0], str):
        venue_name = journal[0]

    source_venue = Source(name=venue_name) if venue_name else None

    # Abstract
    abstract = (work.get("abstract") or "")[:1000]

    # PDF / full-text URLs
    pdf_locations = []
    download_url = work.get("downloadUrl") or ""
    if download_url:
        pdf_locations.append(
            PDFLocation(
                url=download_url,
                source="core",
                is_oa=True,
            )
        )

    # Also check sourceFulltextUrls
    for url in work.get("sourceFulltextUrls", []) or []:
        if url and url not in {loc.url for loc in pdf_locations}:
            pdf_locations.append(PDFLocation(url=url, source="core", is_oa=True))

    return Paper(
        title=title,
        ids=IDSet(doi=doi),
        authors=authors,
        year=year,
        source_venue=source_venue,
        abstract=abstract,
        pdf_locations=pdf_locations,
        is_oa=True,
        data_sources={"core"},
    )

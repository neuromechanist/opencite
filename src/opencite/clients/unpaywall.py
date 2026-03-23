"""Unpaywall API client.

Unpaywall (https://unpaywall.org) provides open access PDF locations for
papers identified by DOI.  It indexes OA copies from 50,000+ publishers
and repositories.

Requires a contact email (``config.contact_email``) -- no API key needed.
Free tier allows up to 100,000 calls per day.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencite.clients.base import BaseClient
from opencite.models import PDFLocation

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.unpaywall.org"


class UnpaywallClient(BaseClient):
    """Client for the Unpaywall REST API.

    Looks up open access PDF locations by DOI.  This is the single most
    effective source for finding free PDFs of paywalled papers.
    """

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=10.0,  # conservative; daily cap is 100k
            burst=5,
        )

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    async def lookup_doi(self, doi: str) -> list[PDFLocation]:
        """Find open access PDF locations for a DOI.

        Returns a list of PDFLocation objects sorted by quality
        (best OA location first).
        """
        email = self.config.contact_email
        if not email:
            logger.debug("Unpaywall requires contact_email; skipping lookup")
            return []

        try:
            resp = await self.get(f"/v2/{doi}", params={"email": email})
        except Exception as e:
            logger.debug("Unpaywall lookup failed for %s: %s", doi, e)
            return []

        data = resp.json()
        return _extract_locations(data)


def _extract_locations(data: dict[str, Any]) -> list[PDFLocation]:
    """Extract PDF locations from an Unpaywall API response."""
    locations: list[PDFLocation] = []
    seen_urls: set[str] = set()

    # Best OA location first
    best = data.get("best_oa_location")
    if best:
        loc = _parse_location(best)
        if loc and loc.url not in seen_urls:
            locations.append(loc)
            seen_urls.add(loc.url)

    # Then all other OA locations
    for oa_loc in data.get("oa_locations", []):
        loc = _parse_location(oa_loc)
        if loc and loc.url not in seen_urls:
            locations.append(loc)
            seen_urls.add(loc.url)

    return locations


def _parse_location(loc: dict[str, Any]) -> PDFLocation | None:
    """Parse a single Unpaywall OA location into a PDFLocation."""
    # Prefer url_for_pdf, fall back to url_for_landing_page
    url = loc.get("url_for_pdf") or ""
    if not url:
        return None

    return PDFLocation(
        url=url,
        source="unpaywall",
        version=loc.get("version", ""),
        is_oa=True,
        license=loc.get("license") or "",
    )

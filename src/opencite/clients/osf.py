"""OSF Preprints API client.

Wraps `https://api.osf.io/v2/preprints/`. A single client covers every
preprint server fronted by OSF -- PsyArXiv, SocArXiv, EarthArXiv,
MetaArXiv, etc. The provider slug is captured in `data_sources` as
``osf:{provider}`` so attribution stays specific without bloating the
canonical `--source` matrix.

API docs: https://developer.osf.io/#operation/preprints_list
No API key required for public preprints.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.osf.io"

# OSF preprints span several DataCite prefixes per provider:
# 10.31234/osf.io/ -- PsyArXiv
# 10.31219/osf.io/ -- OSF Preprints / general
# 10.31222/osf.io/ -- SocArXiv
# 10.31223/X5W -- EarthArXiv (without /osf.io/ segment)
# Be liberal: any DOI containing ``/osf.io/`` is OSF-hosted.
_OSF_DOI_PATTERN = re.compile(r"^10\.\d+/osf\.io/", re.IGNORECASE)


class OSFClient(PreprintClient):
    """Client for the OSF Preprints API."""

    name: ClassVar[str] = "osf"

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.osf_rate_limit,
            burst=5,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
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
        provider: str | None = None,
        **_kwargs: object,
    ) -> list[Paper]:
        """Search OSF Preprints by query string.

        Args:
            query: Free-text search across title and abstract.
            max_results: Maximum results to return (page size).
            provider: Optional provider slug (e.g. ``"psyarxiv"``,
                ``"socarxiv"``) to filter results to one OSF preprint server.
        """
        params: dict[str, Any] = {
            "filter[q]": query,
            "page[size]": min(max_results, 100),
        }
        if provider:
            params["filter[provider]"] = provider

        try:
            resp = await self.get("/v2/preprints/", params=params)
        except APIError as e:
            logger.warning("OSF search failed for query %r: %s", query, e.message)
            return []

        try:
            data = resp.json()
        except ValueError:
            logger.warning("OSF search returned non-JSON for query %r", query)
            return []

        papers: list[Paper] = []
        for item in data.get("data") or []:
            paper = self._parse_item(item)
            if paper is not None:
                papers.append(paper)
        return papers

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up an OSF preprint by DOI.

        OSF Preprint DOIs share an ``/osf.io/`` segment across providers
        (PsyArXiv, SocArXiv, etc.). Non-OSF DOIs return None so the
        orchestrator can route elsewhere.
        """
        if not _OSF_DOI_PATTERN.match(doi.strip()):
            return None

        try:
            resp = await self.get("/v2/preprints/", params={"filter[doi]": doi})
        except APIError as e:
            logger.warning("OSF DOI lookup failed for %s: %s", doi, e.message)
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.warning("OSF DOI lookup returned non-JSON for %s", doi)
            return None

        items = data.get("data") or []
        return self._parse_item(items[0]) if items else None

    # OSF preprints expose a download endpoint; no HTML/JATS shortcut.
    def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
        return FulltextRoute.NONE

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_item(self, item: dict) -> Paper | None:
        attrs = item.get("attributes") or {}
        title = (attrs.get("title") or "").strip()
        if not title:
            return None

        abstract = (attrs.get("description") or "").strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        pub_date = (attrs.get("date_published") or "")[:10]  # YYYY-MM-DD
        year: int | None = None
        if pub_date and pub_date[:4].isdigit():
            year = int(pub_date[:4])

        # OSF JSON:API: ``attributes.doi`` is null for many published
        # preprints (the canonical DOI lives in ``links.preprint_doi`` as a
        # full URL like ``https://doi.org/10.31234/osf.io/<guid>``).
        # Try attributes first, then strip the URL form for the fallback.
        doi = (attrs.get("doi") or "").strip()
        if not doi:
            preprint_doi_url = (item.get("links") or {}).get("preprint_doi") or ""
            if preprint_doi_url:
                # ``https://doi.org/10.31234/osf.io/abc12`` -> ``10.31234/osf.io/abc12``
                doi = re.sub(
                    r"^https?://(dx\.)?doi\.org/", "", preprint_doi_url.strip()
                )
        ids = IDSet(doi=doi)

        # Provider slug for attribution.
        provider = (
            ((item.get("relationships") or {}).get("provider") or {})
            .get("data", {})
            .get("id", "")
        )

        # Tags / subjects -> topics
        topics: list[str] = []
        for tag in attrs.get("tags") or []:
            if isinstance(tag, str) and tag:
                topics.append(tag)

        # Authors are a separate JSON:API endpoint; OSF preprints don't
        # inline them. The dedup pipeline merges author lists from
        # CrossRef/OpenAlex when the same DOI surfaces there.
        authors: list[Author] = []

        # PDF: OSF preprints don't expose a download URL on the preprint
        # object directly (the primary file is a separate JSON:API
        # resource). The redirect endpoint at ``osf.io/download/{guid}``
        # serves the primary file with no extra round-trip.
        pdf_locations: list[PDFLocation] = []
        preprint_id = (item.get("id") or "").strip()
        if preprint_id:
            pdf_locations.append(
                PDFLocation(
                    url=f"https://osf.io/download/{preprint_id}",
                    version="submittedVersion",
                    is_oa=True,
                    source=f"osf:{provider}" if provider else "osf",
                )
            )

        landing = (item.get("links") or {}).get("html") or ""
        url = landing or (f"https://doi.org/{doi}" if doi else "")

        source_venue: Source | None = None
        if provider:
            source_venue = Source(name=f"OSF:{provider}", is_oa=True)
        else:
            source_venue = Source(name="OSF Preprints", is_oa=True)

        attribution = f"osf:{provider}" if provider else "osf"

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
            data_sources={attribution},
        )

    @staticmethod
    def is_osf_doi(doi: str) -> bool:
        """Return True if *doi* points to an OSF-hosted preprint."""
        return bool(_OSF_DOI_PATTERN.match(doi.strip()))

"""Zenodo REST API client.

Wraps `https://zenodo.org/api/records`. CERN-hosted; very broad scope
(datasets, code, theses, preprints). This client filters search to
``resource_type=publication-preprint`` so only preprint records flow into
the orchestrator.

API docs: https://developers.zenodo.org/
Optional access token (`config.zenodo_access_token`) raises rate limits.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://zenodo.org"

# Zenodo Crossref-registered DOI prefix.
_ZENODO_DOI_PREFIX = "10.5281/zenodo."


class ZenodoClient(PreprintClient):
    """Client for the Zenodo REST API."""

    name: ClassVar[str] = "zenodo"

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.zenodo_rate_limit,
            burst=5,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.contact_email:
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        if self.config.zenodo_access_token:
            headers["Authorization"] = f"Bearer {self.config.zenodo_access_token}"
        return headers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 20,
        **_kwargs: object,
    ) -> list[Paper]:
        """Search Zenodo for preprint records matching *query*."""
        params: dict[str, Any] = {
            "q": query,
            "type": "publication",
            "subtype": "preprint",
            "size": min(max_results, 100),
        }
        try:
            resp = await self.get("/api/records", params=params)
        except APIError as e:
            logger.warning("Zenodo search failed for query %r: %s", query, e.message)
            return []

        try:
            data = resp.json()
        except ValueError:
            logger.warning("Zenodo search returned non-JSON for query %r", query)
            return []

        hits = ((data.get("hits") or {}).get("hits")) or []
        papers: list[Paper] = []
        for record in hits:
            paper = self._parse_record(record)
            if paper is not None:
                papers.append(paper)
        return papers

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a Zenodo record by DOI.

        Zenodo DOIs follow ``10.5281/zenodo.<record_id>``. Other DOIs
        return None.
        """
        normalized = doi.strip().lower()
        if not normalized.startswith(_ZENODO_DOI_PREFIX):
            return None
        record_id = normalized[len(_ZENODO_DOI_PREFIX) :]
        if not record_id.isdigit():
            return None

        try:
            resp = await self.get(f"/api/records/{record_id}")
        except APIError as e:
            logger.warning("Zenodo DOI lookup failed for %s: %s", doi, e.message)
            return None

        try:
            record = resp.json()
        except ValueError:
            logger.warning("Zenodo DOI lookup returned non-JSON for %s", doi)
            return None

        return self._parse_record(record)

    def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
        return FulltextRoute.NONE

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_record(self, record: dict) -> Paper | None:
        metadata = record.get("metadata") or {}
        title = (metadata.get("title") or "").strip()
        if not title:
            return None

        abstract = (metadata.get("description") or "").strip()
        if "<" in abstract:
            # Zenodo descriptions can contain HTML; strip tags cheaply.
            import re

            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        pub_date = (metadata.get("publication_date") or "")[:10]
        year: int | None = None
        if pub_date and pub_date[:4].isdigit():
            year = int(pub_date[:4])

        # DOI: ``record["doi"]`` is the version DOI; concept DOI lives in
        # ``record["conceptdoi"]`` if present. Prefer the version DOI for
        # citation stability.
        doi = (record.get("doi") or metadata.get("doi") or "").strip()
        ids = IDSet(doi=doi)

        # Authors
        authors: list[Author] = []
        for creator in metadata.get("creators") or []:
            name = (creator.get("name") or "").strip()
            if not name:
                continue
            # Zenodo names are typically "Family, Given".
            if "," in name:
                family, given = (s.strip() for s in name.split(",", 1))
            else:
                parts = name.rsplit(None, 1)
                family = parts[-1] if parts else name
                given = parts[0] if len(parts) > 1 else ""
            authors.append(Author(name=name, family_name=family, given_name=given))

        topics = list(metadata.get("keywords") or [])

        # Files: pick PDFs.
        pdf_locations: list[PDFLocation] = []
        for fobj in record.get("files") or []:
            key = (fobj.get("key") or "").lower()
            if not key.endswith(".pdf"):
                continue
            url = ((fobj.get("links") or {}).get("self")) or ""
            if url:
                pdf_locations.append(
                    PDFLocation(
                        url=url,
                        version="submittedVersion",
                        is_oa=True,
                        source="zenodo",
                    )
                )

        landing = ((record.get("links") or {}).get("html")) or ""
        url = landing or (f"https://doi.org/{doi}" if doi else "")

        return Paper(
            title=title,
            ids=ids,
            authors=authors,
            year=year,
            source_venue=Source(name="Zenodo", is_oa=True),
            publication_date=pub_date,
            pub_type="preprint",
            abstract=abstract,
            topics=topics,
            is_oa=True,
            url=url,
            pdf_locations=pdf_locations,
            data_sources={"zenodo"},
        )

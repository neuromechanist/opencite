"""Figshare REST API client.

Wraps `https://api.figshare.com/v2/`. Search is filtered to
``item_type=11`` (preprint) so we don't pull in figures, datasets, or
posters. Each preprint provides one or more files; PDFs go into
`pdf_locations` so the existing PDF pipeline can fetch them.

API docs: https://docs.figshare.com/
No API key required for public read access.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.preprint_base import FulltextRoute, PreprintClient
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.figshare.com"

# Figshare's Crossref-registered DOI prefix.
_FIGSHARE_DOI_PREFIX = "10.6084/m9.figshare."

# Figshare item_type for preprints.
_PREPRINT_ITEM_TYPE = 11


class FigshareClient(PreprintClient):
    """Client for the Figshare REST API."""

    name: ClassVar[str] = "figshare"

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.figshare_rate_limit,
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
        **_kwargs: object,
    ) -> list[Paper]:
        """Search Figshare for preprint articles matching *query*."""
        body: dict[str, Any] = {
            "search_for": query,
            "item_type": _PREPRINT_ITEM_TYPE,
            "page_size": min(max_results, 100),
        }
        try:
            resp = await self.post("/v2/articles/search", json=body)
        except APIError as e:
            logger.warning("Figshare search failed for query %r: %s", query, e.message)
            return []

        try:
            items = resp.json()
        except ValueError:
            logger.warning("Figshare search returned non-JSON for query %r", query)
            return []
        if not isinstance(items, list):
            logger.warning("Figshare search returned unexpected payload for %r", query)
            return []

        # Search returns summary items; each needs a per-article GET to
        # populate authors / files / tags. Fan out concurrently -- the
        # rate limiter in BaseClient still serialises one-per-token, so
        # the wall-clock time is bounded by `len(items) / rate_limit`
        # rather than the sequential sum.
        article_ids: list[int | str] = []
        for summary in items:
            article_id = summary.get("id")
            if not article_id:
                logger.warning("Figshare search summary missing id for query %r", query)
                continue
            article_ids.append(article_id)

        full_records = await asyncio.gather(
            *(self._fetch_article(aid) for aid in article_ids),
            return_exceptions=False,
        )

        papers: list[Paper] = []
        for full in full_records:
            if full is None:
                continue
            paper = self._parse_article(full)
            if paper is not None:
                papers.append(paper)
        return papers

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a Figshare article by DOI.

        Figshare DOIs follow ``10.6084/m9.figshare.<id>``. Other DOIs
        return None.
        """
        if not doi.lower().startswith(_FIGSHARE_DOI_PREFIX):
            return None

        # The /v2/articles endpoint accepts a `doi` query parameter and
        # returns a list of summaries; use the first hit.
        try:
            resp = await self.get("/v2/articles", params={"doi": doi})
        except APIError as e:
            logger.warning("Figshare DOI lookup failed for %s: %s", doi, e.message)
            return None

        try:
            items = resp.json()
        except ValueError:
            logger.warning("Figshare DOI lookup returned non-JSON for %s", doi)
            return None
        if not isinstance(items, list) or not items:
            return None

        article_id = items[0].get("id")
        if not article_id:
            return None
        full = await self._fetch_article(article_id)
        return self._parse_article(full) if full is not None else None

    def fulltext_route(self, paper: Paper) -> FulltextRoute:  # noqa: ARG002
        return FulltextRoute.NONE

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_article(self, article_id: int | str) -> dict | None:
        try:
            resp = await self.get(f"/v2/articles/{article_id}")
        except APIError as e:
            logger.warning(
                "Figshare article fetch failed for id %s: %s", article_id, e.message
            )
            return None
        try:
            data = resp.json()
        except ValueError:
            logger.warning(
                "Figshare article fetch returned non-JSON for id %s", article_id
            )
            return None
        return data if isinstance(data, dict) else None

    def _parse_article(self, article: dict) -> Paper | None:
        title = (article.get("title") or "").strip()
        if not title:
            return None

        abstract = (article.get("description") or "").strip()
        if "<" in abstract:
            import re

            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        # Figshare timestamps look like "2024-09-12T00:00:00Z".
        pub_date = (article.get("published_date") or "")[:10]
        year: int | None = None
        if pub_date and pub_date[:4].isdigit():
            year = int(pub_date[:4])

        doi = (article.get("doi") or "").strip()
        ids = IDSet(doi=doi)

        authors: list[Author] = []
        for author in article.get("authors") or []:
            name = (author.get("full_name") or "").strip()
            if not name:
                continue
            parts = name.rsplit(None, 1)
            family = parts[-1] if parts else name
            given = parts[0] if len(parts) > 1 else ""
            authors.append(Author(name=name, family_name=family, given_name=given))

        topics: list[str] = []
        for tag in article.get("tags") or []:
            if isinstance(tag, str) and tag:
                topics.append(tag)

        pdf_locations: list[PDFLocation] = []
        for fobj in article.get("files") or []:
            name = (fobj.get("name") or "").lower()
            if not name.endswith(".pdf"):
                continue
            url = (fobj.get("download_url") or "").strip()
            if url:
                pdf_locations.append(
                    PDFLocation(
                        url=url,
                        version="submittedVersion",
                        is_oa=True,
                        source="figshare",
                    )
                )

        landing = (article.get("figshare_url") or "").strip()
        url = landing or (f"https://doi.org/{doi}" if doi else "")

        return Paper(
            title=title,
            ids=ids,
            authors=authors,
            year=year,
            source_venue=Source(name="Figshare", is_oa=True),
            publication_date=pub_date,
            pub_type="preprint",
            abstract=abstract,
            topics=topics,
            is_oa=True,
            url=url,
            pdf_locations=pdf_locations,
            data_sources={"figshare"},
        )

"""Shared base for bioRxiv-style preprint clients (bioRxiv + medRxiv).

bioRxiv and medRxiv share the same DOI prefix (10.1101), the same CrossRef
keyword-search path, and the same Content API (`api.biorxiv.org`) URL shape.
The only differences are:

- the `server` segment in Content API URLs (`/details/{server}/{doi}`)
- the public site domain used for landing-page and PDF URLs
  (`www.biorxiv.org` vs `www.medrxiv.org`)
- the value used in `data_sources` and `Source.name` for attribution

Subclasses set the `name` and `server` class attributes; everything else is
inherited.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from opencite.clients.preprint_base import PreprintClient
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

_BIORXIV_BASE = "https://api.biorxiv.org"
_CROSSREF_BASE = "https://api.crossref.org"

# CrossRef "type" for preprints
_PREPRINT_TYPE = "posted-content"


class _BiorxivLikePreprintClient(PreprintClient):
    """Internal base class for bioRxiv- and medRxiv-style preprint clients.

    Subclasses set ``name`` (e.g. "biorxiv") and ``server`` (the segment used
    in bioRxiv Content API URLs and the public site domain).
    """

    server: ClassVar[str]

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=_BIORXIV_BASE,
            rate_limit=config.biorxiv_rate_limit,
            burst=5,
        )
        self._crossref_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> _BiorxivLikePreprintClient:
        await super().__aenter__()
        self._crossref_client = httpx.AsyncClient(
            base_url=_CROSSREF_BASE,
            timeout=self.timeout,
            headers=self._default_headers(),
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._crossref_client:
            await self._crossref_client.aclose()
            self._crossref_client = None
        await super().__aexit__(*args)

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.contact_email:
            # CrossRef polite-pool header
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        return headers

    # ------------------------------------------------------------------
    # Public API (PreprintClient)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        max_results: int = 20,
        **_kwargs: object,
    ) -> list[Paper]:
        """Search this server's preprints via CrossRef.

        CrossRef returns both bioRxiv and medRxiv records under the shared
        ``prefix:10.1101`` filter, so each subclass post-filters to its own
        ``server`` to keep attribution clean.
        """
        if self._crossref_client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        params: dict[str, Any] = {
            "query.bibliographic": query,
            "filter": f"prefix:10.1101,type:{_PREPRINT_TYPE}",
            # Ask CrossRef for more rows than requested because we will
            # post-filter on container-title.
            "rows": min(max_results * 2, 100),
            "select": (
                "DOI,title,author,published,created,abstract,"
                "container-title,URL,is-referenced-by-count"
            ),
        }
        if self.config.contact_email:
            params["mailto"] = self.config.contact_email

        data: dict = {}
        await self.rate_limiter.acquire()
        try:
            resp = await self._crossref_client.get("/works", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "CrossRef search HTTP %d for query %r",
                e.response.status_code,
                query,
            )
            return []
        except httpx.TimeoutException:
            logger.warning("CrossRef search timed out for query %r", query)
            return []
        except httpx.RequestError as e:
            logger.warning("CrossRef search network error for query %r: %s", query, e)
            return []
        except ValueError as e:
            # json.JSONDecodeError is a subclass of ValueError
            logger.warning(
                "CrossRef search returned non-JSON for query %r: %s", query, e
            )
            return []

        papers: list[Paper] = []
        for item in (data.get("message") or {}).get("items") or []:
            paper = self._parse_crossref_item(item)
            if paper:
                papers.append(paper)
            if len(papers) >= max_results:
                break
        return papers

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a single preprint on this server by DOI.

        Hits only this server's Content API endpoint. Callers (typically the
        search orchestrator) can fan out to multiple servers in parallel when
        the server is unknown.
        """
        try:
            resp = await self.get(f"/details/{self.server}/{doi}")
        except APIError as e:
            logger.warning(
                "%s Content API error for DOI %s: %s",
                self.server,
                doi,
                e.message,
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.warning(
                "%s Content API returned non-JSON for DOI %s",
                self.server,
                doi,
            )
            return None

        collection = data.get("collection") or []
        if not collection:
            logger.debug("%s: DOI %s not found", self.server, doi)
            return None

        entry = collection[-1]
        return self._parse_content_entry(entry, server=self.server)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_content_entry(
        self, entry: dict, server: str | None = None
    ) -> Paper | None:
        """Parse a single record from the bioRxiv Content API."""
        srv = server or self.server
        doi = (entry.get("doi") or "").strip()
        title = (entry.get("title") or "").strip()
        if not title:
            return None

        version = str(entry.get("version") or "1")
        ids = IDSet(doi=doi)

        # Date
        date_str = (entry.get("date") or "")[:10]  # "YYYY-MM-DD"
        year: int | None = None
        if date_str and date_str[:4].isdigit():
            year = int(date_str[:4])

        # Authors -- stored as "Smith J; Jones AB; ..."
        raw_authors = entry.get("authors") or ""
        authors: list[Author] = []
        if raw_authors:
            for raw in str(raw_authors).split(";"):
                name = raw.strip()
                if not name:
                    continue
                parts = name.split()
                family = parts[0] if parts else name
                given = " ".join(parts[1:]) if len(parts) > 1 else ""
                authors.append(Author(name=name, family_name=family, given_name=given))

        abstract = (entry.get("abstract") or "").strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        category = (entry.get("category") or "").strip()
        topics = [category] if category else []
        source_venue = Source(name=srv.capitalize(), is_oa=True)

        # Direct PDF URL: bioRxiv always provides versioned PDFs
        pdf_locations: list[PDFLocation] = []
        if doi:
            pdf_url = f"https://www.{srv}.org/content/{doi}v{version}.full.pdf"
            pdf_locations.append(
                PDFLocation(
                    url=pdf_url,
                    version="submittedVersion",
                    is_oa=True,
                    source=srv,
                )
            )

        url = f"https://www.{srv}.org/content/{doi}v{version}" if doi else ""

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
            data_sources={srv},
        )

    def _parse_crossref_item(self, item: dict) -> Paper | None:
        """Parse a CrossRef works item into a Paper, filtered to this server.

        Returns None when the item's container-title doesn't match this
        client's server, so each client only emits papers it owns.
        """
        doi = (item.get("DOI") or "").strip()
        titles = item.get("title") or []
        title = titles[0].strip() if titles else ""
        if not title:
            return None

        # Determine server from container-title and filter to this client's
        # server. CrossRef's container-title field reliably distinguishes
        # bioRxiv from medRxiv even though they share the 10.1101 DOI prefix.
        container = item.get("container-title") or []
        container_name = container[0].lower() if container else ""
        # Default to biorxiv for empty/unknown container-titles.
        item_server = "medrxiv" if "medrxiv" in container_name else "biorxiv"
        if item_server != self.server:
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
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        source_venue = Source(name=item_server.capitalize(), is_oa=True)

        # PDF URL
        pdf_locations: list[PDFLocation] = []
        if doi:
            pdf_url = f"https://www.{item_server}.org/content/{doi}v1.full.pdf"
            pdf_locations.append(
                PDFLocation(
                    url=pdf_url,
                    version="submittedVersion",
                    is_oa=True,
                    source=item_server,
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
            data_sources={item_server},
        )

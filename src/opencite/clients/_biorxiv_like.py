"""Shared base for bioRxiv-style preprint clients (bioRxiv + medRxiv).

bioRxiv and medRxiv share the same DOI prefixes (10.1101, and 10.64898
for newer openRxiv preprints), the same CrossRef keyword-search path, and
the same Content API (`api.biorxiv.org`) URL shape. The only differences
are:

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

from opencite.clients.crossref import CrossRefClient
from opencite.clients.preprint_base import (
    FulltextRoute,
    PreprintClient,
    html_to_markdown,
)
from opencite.exceptions import APIError
from opencite.models import Author, IDSet, Paper, PDFLocation, Source
from opencite.utils import is_openrxiv_doi

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

_BIORXIV_BASE = "https://api.biorxiv.org"

# CrossRef "type" for preprints
_PREPRINT_TYPE = "posted-content"

# CrossRef's `prefix` filter matches the depositing member's owner prefix,
# not the DOI string. bioRxiv/medRxiv DOIs keep the 10.1101 prefix, but
# their records are now deposited by openRxiv under owner prefix 10.64898;
# repeating a filter name ORs the values.
_CROSSREF_FILTER = f"prefix:10.1101,prefix:10.64898,type:{_PREPRINT_TYPE}"


class _BiorxivLikePreprintClient(PreprintClient):
    """Internal base class for bioRxiv- and medRxiv-style preprint clients.

    Subclasses set ``name`` (e.g. "biorxiv") and ``server`` (the segment used
    in bioRxiv Content API URLs and the public site domain).
    """

    server: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith("_"):
            return
        if not getattr(cls, "__abstractmethods__", None) and not hasattr(cls, "server"):
            raise TypeError(f"{cls.__name__} must declare a `server` class attribute")

    def __init__(self, config: Config) -> None:
        super().__init__(
            config=config,
            base_url=_BIORXIV_BASE,
            rate_limit=config.biorxiv_rate_limit,
            burst=5,
        )
        # Keyword search goes through CrossRef; using CrossRefClient shares
        # its process-wide rate/concurrency budget and 429 retry handling.
        self._crossref = CrossRefClient(config)

    async def __aenter__(self) -> _BiorxivLikePreprintClient:
        await super().__aenter__()
        try:
            await self._crossref.__aenter__()
        except Exception:
            # The parent's session was opened above; close it before
            # propagating so we don't leak the underlying httpx client.
            await super().__aexit__()
            raise
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._crossref.__aexit__(*args)
        await super().__aexit__(*args)

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.contact_email:
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
        openRxiv prefix filter, so each subclass post-filters to its own
        ``server`` to keep attribution clean.

        Raises `APIError` when CrossRef fails so the orchestrator can report
        the source as failed rather than empty.
        """
        papers: list[Paper] = []
        for item in await self._crossref.query_works(_crossref_search_params(query)):
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
        return self._parse_content_entry(entry)

    # ------------------------------------------------------------------
    # Full-text retrieval (bioRxiv/medRxiv .full HTML)
    # ------------------------------------------------------------------

    def fulltext_route(self, paper: Paper) -> FulltextRoute:
        """`.full` HTML when an openRxiv DOI is present, else NONE."""
        doi = (paper.doi or "").strip()
        return FulltextRoute.HTML if is_openrxiv_doi(doi) else FulltextRoute.NONE

    async def fetch_fulltext(self, paper: Paper) -> str | None:
        """Fetch the bioRxiv/medRxiv `.full` HTML and return markdown.

        Both servers expose articles at
        ``https://www.{server}.org/content/{doi}.full`` (the same URL as the
        PDF route minus the ``.pdf``). Returns None on missing DOI, non-200
        response, or markdown conversion failure.
        """
        doi = (paper.doi or "").strip()
        if not is_openrxiv_doi(doi):
            return None

        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")

        url = f"https://www.{self.server}.org/content/{doi}.full"
        try:
            await self.rate_limiter.acquire()
            resp = await self._client.get(url, follow_redirects=True)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning("%s .full fetch failed for %s: %s", self.server, doi, e)
            return None

        if resp.status_code != 200:
            logger.warning(
                "%s .full returned HTTP %d for %s",
                self.server,
                resp.status_code,
                doi,
            )
            return None

        return html_to_markdown(resp.text, context=f"{self.server}:{doi}")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_content_entry(self, entry: dict) -> Paper | None:
        """Parse a single record from the bioRxiv Content API."""
        srv = self.server
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

        Returns None when the item belongs to the other server, so each
        client only emits papers it owns.
        """
        doi = (item.get("DOI") or "").strip()
        titles = item.get("title") or []
        title = titles[0].strip() if titles else ""
        if not title:
            return None

        item_server = _crossref_item_server(item)
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


def _crossref_search_params(query: str) -> dict[str, Any]:
    """CrossRef ``/works`` params for an openRxiv keyword search.

    The params do not depend on the server, so bioRxiv and medRxiv searches
    for the same query coalesce into one CrossRef request.
    """
    return {
        "query.bibliographic": query,
        "filter": _CROSSREF_FILTER,
        # bioRxiv and medRxiv hits come back interleaved and each client
        # keeps only its own server's, so fetch a full page.
        "rows": 100,
        "select": (
            "DOI,title,author,published,created,abstract,"
            "container-title,resource,URL,is-referenced-by-count"
        ),
    }


def _crossref_item_server(item: dict) -> str:
    """Return ``"medrxiv"`` or ``"biorxiv"`` for an openRxiv CrossRef item.

    openRxiv deposits omit ``container-title``; the primary resource URL
    (``http://medrxiv.org/lookup/doi/...``) still identifies the server.
    Older deposits carry the server as container-title. (The ``institution``
    field also names the server but cannot be requested via ``select``.)
    Unknown items default to bioRxiv.
    """
    primary_url = ((item.get("resource") or {}).get("primary") or {}).get("URL") or ""
    container = item.get("container-title") or []
    signals = " ".join([primary_url, *container]).lower()
    return "medrxiv" if "medrxiv" in signals else "biorxiv"

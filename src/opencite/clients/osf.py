"""OSF Preprints API client.

Wraps `https://api.osf.io/v2/preprints/`. A single client covers every
preprint server fronted by OSF -- PsyArXiv, SocArXiv, EarthArXiv,
MetaArXiv, etc. The provider slug is captured in `data_sources` as
``osf:{provider}`` so attribution stays specific without bloating the
canonical `--source` matrix.

The v2 preprints endpoint has no free-text filter, so keyword search goes
through SHARE (`share.osf.io/api/v3/index-card-search`), the index behind
osf.io search, and the ranked hits are hydrated from the v2 endpoint.

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
SHARE_SEARCH_URL = "https://share.osf.io/api/v3/index-card-search"
_OSF_ORIGIN = "https://osf.io"
_PAGE_SIZE_CAP = 100

# OSF preprint IDs carry a version suffix in the v2 API (``abc12_v2``).
_VERSION_SUFFIX = re.compile(r"_v\d+$")
# SHARE identifies OSF resources by URL, e.g. ``https://osf.io/abc12``.
_OSF_RESOURCE_URL = re.compile(r"^https?://osf\.io/([A-Za-z0-9]+)/?$")

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
            query: Free-text search across title, abstract, and contributors.
            max_results: Maximum results to return (page size).
            provider: Optional provider slug (e.g. ``"psyarxiv"``,
                ``"socarxiv"``) to filter results to one OSF preprint server.
        """
        size = min(max_results, _PAGE_SIZE_CAP)
        resp = await self.get(
            SHARE_SEARCH_URL, params=_share_search_params(query, size, provider)
        )
        ranked_ids = _share_result_ids(resp.json())
        if not ranked_ids:
            return []

        resp = await self.get(
            "/v2/preprints/",
            params={"filter[id]": ",".join(ranked_ids), "page[size]": size},
        )
        items = _rank_by_share_order(resp.json().get("data") or [], ranked_ids)
        papers: list[Paper] = []
        for item in items:
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


def _share_search_params(
    query: str, size: int, provider: str | None = None
) -> dict[str, Any]:
    """Query parameters for a SHARE index-card search over OSF preprints."""
    params: dict[str, Any] = {
        "cardSearchText": query,
        "cardSearchFilter[resourceType]": "Preprint",
        "cardSearchFilter[accessService]": _OSF_ORIGIN,
        "page[size]": size,
        "acceptMediatype": "application/vnd.api+json",
    }
    if provider:
        params["cardSearchFilter[publisher]"] = f"{_OSF_ORIGIN}/preprints/{provider}"
    return params


def _rank_by_share_order(
    items: list[dict[str, Any]], ranked_ids: list[str]
) -> list[dict[str, Any]]:
    """Order v2 preprint records by SHARE rank.

    ``filter[id]`` returns records in arbitrary order and with versioned IDs
    (``abc12_v1``), so the version suffix is stripped before matching.
    Unranked records go last.
    """
    rank = {osf_id: i for i, osf_id in enumerate(ranked_ids)}
    return sorted(
        items,
        key=lambda item: rank.get(
            _VERSION_SUFFIX.sub("", str(item.get("id", ""))), len(rank)
        ),
    )


def _share_result_ids(data: dict[str, Any]) -> list[str]:
    """Extract OSF IDs, in rank order, from a SHARE index-card-search payload.

    The JSON:API payload lists ranked ``search-result`` references under
    ``data.relationships.searchResultPage``; each points at an ``index-card``
    in ``included`` whose ``resourceMetadata["@id"]`` is the OSF URL.

    Raises `APIError` when the page has results but none parse to an OSF
    ID, so a payload shape change surfaces as a failure rather than as an
    empty result.
    """
    included = {
        (item.get("type"), item.get("id")): item for item in data.get("included") or []
    }
    page = (
        ((data.get("data") or {}).get("relationships") or {}).get("searchResultPage")
        or {}
    ).get("data") or []

    ids: list[str] = []
    for ref in page:
        result = included.get(("search-result", ref.get("id"))) or {}
        card_ref = ((result.get("relationships") or {}).get("indexCard") or {}).get(
            "data"
        ) or {}
        card = included.get(("index-card", card_ref.get("id"))) or {}
        resource_url = (
            (card.get("attributes") or {}).get("resourceMetadata") or {}
        ).get("@id") or ""
        match = _OSF_RESOURCE_URL.match(resource_url)
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    if page and not ids:
        raise APIError(
            f"SHARE returned {len(page)} results but no OSF IDs could be parsed"
        )
    return ids

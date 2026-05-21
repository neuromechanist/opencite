"""OpenAlex API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from opencite.clients.base import BaseClient
from opencite.models import Author, IDSet, Paper, PDFLocation, Source
from opencite.utils import reconstruct_abstract

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"


class OpenAlexClient(BaseClient):
    """Client for the OpenAlex API.

    Uses httpx directly (not pyalex) for consistency with other clients
    and to integrate rate limiting through the BaseClient.

    Shares a process-wide rate limiter so concurrent search and citation
    callers don't multiply requests past the per-key OpenAlex budget.
    """

    shared_limiter_key: ClassVar[str | None] = "openalex"

    def __init__(self, config: Config):
        super().__init__(
            config=config,
            base_url=BASE_URL,
            rate_limit=config.openalex_rate_limit,
            burst=10,
        )

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.openalex_api_key:
            headers["Authorization"] = f"Bearer {self.config.openalex_api_key}"
        if self.config.contact_email:
            headers["User-Agent"] = f"opencite/0.1 (mailto:{self.config.contact_email})"
        return headers

    async def search(
        self,
        query: str,
        max_results: int = 20,
        year_from: int | None = None,
        year_to: int | None = None,
        oa_only: bool = False,
        sort: str = "relevance",
    ) -> list[Paper]:
        """Search for papers by keyword query."""
        params: dict[str, Any] = {
            "search": query,
            "per-page": min(max_results, 200),
            "select": _WORK_FIELDS,
        }

        filters = []
        if year_from and year_to:
            filters.append(f"publication_year:{year_from}-{year_to}")
        elif year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        elif year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if oa_only:
            filters.append("is_oa:true")
        if filters:
            params["filter"] = ",".join(filters)

        if sort == "citations":
            params["sort"] = "cited_by_count:desc"
        elif sort == "year":
            params["sort"] = "publication_date:desc"
        # "relevance" is default when using search parameter

        resp = await self.get("/works", params=params)
        data = resp.json()
        return [self._parse_work(w) for w in data.get("results", []) if w.get("title")]

    async def lookup_doi(self, doi: str) -> Paper | None:
        """Look up a single paper by DOI."""
        try:
            resp = await self.get(
                f"/works/doi:{doi}",
                params={"select": _WORK_FIELDS},
            )
            return self._parse_work(resp.json())
        except Exception:
            logger.debug("OpenAlex DOI lookup failed for %s", doi)
            return None

    async def lookup_pmid(self, pmid: str) -> Paper | None:
        """Look up a single paper by PubMed ID."""
        try:
            resp = await self.get(
                f"/works/pmid:{pmid}",
                params={"select": _WORK_FIELDS},
            )
            return self._parse_work(resp.json())
        except Exception:
            logger.debug("OpenAlex PMID lookup failed for %s", pmid)
            return None

    async def lookup_pmcid(self, pmcid: str) -> Paper | None:
        """Look up a single paper by PMC ID."""
        try:
            resp = await self.get(
                f"/works/pmcid:{pmcid}",
                params={"select": _WORK_FIELDS},
            )
            return self._parse_work(resp.json())
        except Exception:
            logger.debug("OpenAlex PMCID lookup failed for %s", pmcid)
            return None

    async def citing_papers(
        self,
        openalex_id: str,
        max_results: int = 50,
        sort: str = "citations",
    ) -> list[Paper]:
        """Find papers citing the given work."""
        params: dict[str, Any] = {
            "filter": f"cites:{openalex_id}",
            "per-page": min(max_results, 200),
            "select": _WORK_FIELDS,
        }
        if sort == "citations":
            params["sort"] = "cited_by_count:desc"
        elif sort == "year":
            params["sort"] = "publication_date:desc"

        resp = await self.get("/works", params=params)
        data = resp.json()
        return [self._parse_work(w) for w in data.get("results", []) if w.get("title")]

    async def references(self, openalex_id: str, max_results: int = 50) -> list[Paper]:
        """Find papers referenced by the given work."""
        params: dict[str, Any] = {
            "filter": f"cited_by:{openalex_id}",
            "per-page": min(max_results, 200),
            "select": _WORK_FIELDS,
        }
        resp = await self.get("/works", params=params)
        data = resp.json()
        return [self._parse_work(w) for w in data.get("results", []) if w.get("title")]

    async def canonical_search(
        self,
        query: str,
        max_results: int = 10,
        year_from: int | None = None,
        min_citations: int = 100,
    ) -> list[Paper]:
        """Find the most-cited papers in a field.

        Searches OpenAlex sorted by citation count descending,
        filtered by minimum citations and optional year range.
        """
        filters = [f"cited_by_count:>{min_citations}"]
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")

        params: dict[str, Any] = {
            "search": query,
            "filter": ",".join(filters),
            "sort": "cited_by_count:desc",
            "per-page": min(max_results, 200),
            "select": _WORK_FIELDS,
        }
        resp = await self.get("/works", params=params)
        data = resp.json()
        return [self._parse_work(w) for w in data.get("results", []) if w.get("title")]

    async def batch_lookup_dois(self, dois: list[str]) -> list[Paper]:
        """Batch lookup up to 50 DOIs using filter pipe."""
        papers: list[Paper] = []
        for i in range(0, len(dois), 50):
            chunk = dois[i : i + 50]
            doi_filter = "|".join(f"https://doi.org/{d}" for d in chunk)
            try:
                resp = await self.get(
                    "/works",
                    params={
                        "filter": f"doi:{doi_filter}",
                        "per-page": 50,
                        "select": _WORK_FIELDS,
                    },
                )
                data = resp.json()
                for w in data.get("results", []):
                    if w.get("title"):
                        papers.append(self._parse_work(w))
            except Exception:
                logger.warning("OpenAlex batch DOI lookup failed for chunk at %d", i)
        return papers

    def _parse_work(self, work: dict) -> Paper:
        """Parse an OpenAlex work JSON object into a Paper model."""
        # DOI
        doi_raw = work.get("doi") or ""
        doi = doi_raw.replace("https://doi.org/", "").strip()

        # IDs
        oa_id = work.get("id", "")
        if oa_id.startswith("https://openalex.org/"):
            oa_id = oa_id.replace("https://openalex.org/", "")

        # Extract PMID and PMCID from ids object
        ids_obj = work.get("ids") or {}
        pmid = (
            (ids_obj.get("pmid") or "")
            .replace("https://pubmed.ncbi.nlm.nih.gov/", "")
            .rstrip("/")
        )
        pmcid = ids_obj.get("pmcid") or ""

        ids = IDSet(
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            openalex_id=oa_id,
        )

        # Year
        year_str = (work.get("publication_date") or "")[:4]
        year = int(year_str) if year_str and year_str.isdigit() else None

        # Authors
        authors = []
        for a in (work.get("authorships") or [])[:50]:
            author_obj = a.get("author") or {}
            name = author_obj.get("display_name", "")
            if not name:
                continue
            orcid = (author_obj.get("orcid") or "").replace("https://orcid.org/", "")
            author_oa_id = (author_obj.get("id") or "").replace(
                "https://openalex.org/", ""
            )
            parts = name.rsplit(None, 1)
            family = parts[-1] if parts else name
            given = parts[0] if len(parts) > 1 else ""
            authors.append(
                Author(
                    name=name,
                    family_name=family,
                    given_name=given,
                    orcid=orcid,
                    openalex_id=author_oa_id,
                )
            )

        # Abstract
        abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
        if len(abstract) > 1000:
            abstract = abstract[:1000]

        # Source venue
        loc = work.get("primary_location") or {}
        source_info = loc.get("source") or {}
        source_venue = None
        source_name = source_info.get("display_name", "")
        if source_name:
            source_oa_id = (source_info.get("id") or "").replace(
                "https://openalex.org/", ""
            )
            source_venue = Source(
                name=source_name,
                issn=source_info.get("issn_l", "") or "",
                publisher=(source_info.get("host_organization_name") or ""),
                is_oa=source_info.get("is_oa", False) or False,
                openalex_id=source_oa_id,
            )

        # PDF locations
        pdf_locations = _extract_pdf_locations(work)

        # Topics
        topics = []
        for t in (work.get("topics") or [])[:5]:
            display = t.get("display_name", "")
            if display:
                topics.append(display)

        # MeSH
        mesh_terms = []
        for m in work.get("mesh") or []:
            name = m.get("descriptor_name", "")
            if name:
                mesh_terms.append(name)

        # Funders
        grants = []
        for f in work.get("funders") or []:
            grant: dict[str, str] = {}
            funder = f.get("display_name", "")
            award_ids = f.get("award_ids") or []
            if funder:
                grant["funder"] = funder
            if award_ids:
                grant["award_id"] = award_ids[0]
            if grant:
                grants.append(grant)

        # OA status
        oa_obj = work.get("open_access") or {}
        is_oa = oa_obj.get("is_oa", False) or False

        return Paper(
            title=work.get("title", ""),
            ids=ids,
            authors=authors,
            year=year,
            source_venue=source_venue,
            publication_date=work.get("publication_date") or "",
            pub_type=work.get("type", ""),
            abstract=abstract,
            topics=topics,
            mesh_terms=mesh_terms,
            citation_count=work.get("cited_by_count", 0) or 0,
            is_retracted=work.get("is_retracted", False) or False,
            url=doi_raw if doi_raw else work.get("id", ""),
            pdf_locations=pdf_locations,
            is_oa=is_oa,
            data_sources={"openalex"},
            grants=grants,
        )


def _extract_pdf_locations(work: dict) -> list[PDFLocation]:
    """Extract all known PDF locations from an OpenAlex work."""
    locations: list[PDFLocation] = []
    seen_urls: set[str] = set()

    # Best OA location first
    best_oa = work.get("best_oa_location")
    if best_oa:
        _add_location(best_oa, locations, seen_urls)

    # Primary location
    primary = work.get("primary_location")
    if primary:
        _add_location(primary, locations, seen_urls)

    # All other locations
    for loc in work.get("locations") or []:
        _add_location(loc, locations, seen_urls)

    return locations


def _add_location(loc: dict, locations: list[PDFLocation], seen_urls: set[str]) -> None:
    """Add a PDF location if it has a URL we haven't seen."""
    pdf_url = loc.get("pdf_url") or ""
    if not pdf_url or pdf_url in seen_urls:
        return
    seen_urls.add(pdf_url)
    locations.append(
        PDFLocation(
            url=pdf_url,
            source="openalex",
            version=loc.get("version") or "",
            is_oa=loc.get("is_oa", False) or False,
            license=loc.get("license") or "",
        )
    )


# Fields to request (reduces payload size)
_WORK_FIELDS = ",".join(
    [
        "id",
        "doi",
        "ids",
        "title",
        "abstract_inverted_index",
        "publication_date",
        "type",
        "authorships",
        "primary_location",
        "best_oa_location",
        "locations",
        "cited_by_count",
        "is_retracted",
        "open_access",
        "topics",
        "mesh",
        "funders",
    ]
)

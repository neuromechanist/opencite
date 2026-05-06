"""Search orchestrator for parallel multi-source search."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from opencite.clients.arxiv import ArXivClient
from opencite.clients.biorxiv import BioRxivClient
from opencite.clients.core import COREClient
from opencite.clients.crossref import CrossRefClient
from opencite.clients.figshare import FigshareClient
from opencite.clients.medrxiv import MedRxivClient
from opencite.clients.openalex import OpenAlexClient
from opencite.clients.osf import OSFClient
from opencite.clients.pubmed import PubMedClient
from opencite.clients.semantic_scholar import SemanticScholarClient
from opencite.clients.zenodo import ZenodoClient
from opencite.dedup import deduplicate
from opencite.models import IDType, Paper, SearchResult, parse_identifier

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)

ALL_SOURCES = (
    "openalex",
    "s2",
    "pubmed",
    "arxiv",
    "biorxiv",
    "medrxiv",
    "osf",
    "zenodo",
    "figshare",
    "crossref",
    "core",
)


class SearchOrchestrator:
    """Coordinates parallel search across all API clients.

    Usage::

        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search("deep learning")
            for paper in result.papers:
                print(paper.title)
    """

    def __init__(self, config: Config):
        self.config = config
        self._openalex = OpenAlexClient(config)
        self._s2 = SemanticScholarClient(config)
        self._pubmed = PubMedClient(config)
        self._arxiv = ArXivClient(config)
        self._biorxiv = BioRxivClient(config)
        self._medrxiv = MedRxivClient(config)
        self._osf = OSFClient(config)
        self._zenodo = ZenodoClient(config)
        self._figshare = FigshareClient(config)
        self._crossref = CrossRefClient(config)
        self._core = COREClient(config)

    async def __aenter__(self) -> SearchOrchestrator:
        await self._openalex.__aenter__()
        await self._s2.__aenter__()
        await self._pubmed.__aenter__()
        await self._arxiv.__aenter__()
        await self._biorxiv.__aenter__()
        await self._medrxiv.__aenter__()
        await self._osf.__aenter__()
        await self._zenodo.__aenter__()
        await self._figshare.__aenter__()
        await self._crossref.__aenter__()
        await self._core.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._openalex.__aexit__()
        await self._s2.__aexit__()
        await self._pubmed.__aexit__()
        await self._arxiv.__aexit__()
        await self._biorxiv.__aexit__()
        await self._medrxiv.__aexit__()
        await self._osf.__aexit__()
        await self._zenodo.__aexit__()
        await self._figshare.__aexit__()
        await self._crossref.__aexit__()
        await self._core.__aexit__()

    async def search(
        self,
        query: str,
        max_results: int = 20,
        sources: tuple[str, ...] | list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        oa_only: bool = False,
        sort: str = "relevance",
    ) -> SearchResult:
        """Search for papers across all configured sources.

        Returns a SearchResult with deduplicated, merged papers.
        """
        if sources is None:
            sources = ALL_SOURCES

        tasks: dict[str, asyncio.Task[list[Paper]]] = {}

        if "openalex" in sources:
            tasks["openalex"] = asyncio.create_task(
                self._search_openalex(
                    query, max_results, year_from, year_to, oa_only, sort
                )
            )
        if "s2" in sources:
            tasks["s2"] = asyncio.create_task(self._search_s2(query, max_results))
        if "pubmed" in sources:
            tasks["pubmed"] = asyncio.create_task(
                self._search_pubmed(query, max_results)
            )
        if "arxiv" in sources:
            tasks["arxiv"] = asyncio.create_task(
                self._search_arxiv(query, max_results, year_from, year_to)
            )
        if "biorxiv" in sources:
            tasks["biorxiv"] = asyncio.create_task(
                self._search_biorxiv(query, max_results)
            )
        if "medrxiv" in sources:
            tasks["medrxiv"] = asyncio.create_task(
                self._search_medrxiv(query, max_results)
            )
        if "osf" in sources:
            tasks["osf"] = asyncio.create_task(self._search_osf(query, max_results))
        if "zenodo" in sources:
            tasks["zenodo"] = asyncio.create_task(
                self._search_zenodo(query, max_results)
            )
        if "figshare" in sources:
            tasks["figshare"] = asyncio.create_task(
                self._search_figshare(query, max_results)
            )
        if "crossref" in sources:
            tasks["crossref"] = asyncio.create_task(
                self._search_crossref(query, max_results, year_from, year_to)
            )
        if "core" in sources:
            tasks["core"] = asyncio.create_task(self._search_core(query, max_results))

        all_papers: list[Paper] = []
        source_counts: dict[str, int] = {}

        for source_name, task in tasks.items():
            try:
                papers = await task
                source_counts[source_name] = len(papers)
                all_papers.extend(papers)
            except Exception as exc:
                logger.warning("Search failed for source %s: %s", source_name, exc)
                source_counts[source_name] = 0

        # Deduplicate and merge
        total_before = len(all_papers)
        unique = deduplicate(all_papers)

        # Sort
        unique = _sort_papers(unique, sort)

        # Limit results
        unique = unique[:max_results]

        return SearchResult(
            query=query,
            papers=unique,
            total_by_source=source_counts,
            deduplicated_count=total_before - len(unique),
        )

    async def lookup(
        self,
        identifier: str,
        enrich: bool = False,
    ) -> Paper | None:
        """Look up a single paper by identifier.

        Auto-detects identifier type (DOI, PMID, PMCID, ArXiv, S2, OpenAlex).
        If enrich=True, fetches from all APIs and merges.
        """
        id_type, id_value = parse_identifier(identifier)
        paper = await self._lookup_by_type(id_type, id_value)

        if paper and enrich:
            paper = await self._enrich(paper)

        return paper

    async def batch_lookup(
        self,
        identifiers: list[str],
        enrich: bool = False,
    ) -> list[Paper]:
        """Look up multiple papers by identifiers."""
        tasks = [self.lookup(ident, enrich=enrich) for ident in identifiers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        papers = []
        for r in results:
            if isinstance(r, Paper):
                papers.append(r)
            elif isinstance(r, Exception):
                logger.warning("Lookup failed: %s", r)
        return papers

    async def _search_openalex(
        self,
        query: str,
        max_results: int,
        year_from: int | None,
        year_to: int | None,
        oa_only: bool,
        sort: str,
    ) -> list[Paper]:
        return await self._openalex.search(
            query,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
            oa_only=oa_only,
            sort=sort,
        )

    async def _search_s2(self, query: str, max_results: int) -> list[Paper]:
        return await self._s2.search(query, max_results=max_results)

    async def _search_pubmed(self, query: str, max_results: int) -> list[Paper]:
        return await self._pubmed.search(query, max_results=max_results)

    async def _search_arxiv(
        self,
        query: str,
        max_results: int,
        year_from: int | None,
        year_to: int | None,
    ) -> list[Paper]:
        return await self._arxiv.search(
            query,
            max_results=max_results,
            year_from=year_from,
            year_to=year_to,
        )

    async def _search_biorxiv(self, query: str, max_results: int) -> list[Paper]:
        return await self._biorxiv.search(query, max_results=max_results)

    async def _search_medrxiv(self, query: str, max_results: int) -> list[Paper]:
        return await self._medrxiv.search(query, max_results=max_results)

    async def _search_osf(self, query: str, max_results: int) -> list[Paper]:
        return await self._osf.search(query, max_results=max_results)

    async def _search_zenodo(self, query: str, max_results: int) -> list[Paper]:
        return await self._zenodo.search(query, max_results=max_results)

    async def _search_figshare(self, query: str, max_results: int) -> list[Paper]:
        return await self._figshare.search(query, max_results=max_results)

    async def _search_crossref(
        self,
        query: str,
        max_results: int,
        year_from: int | None,
        year_to: int | None,
    ) -> list[Paper]:
        return await self._crossref.search(
            query, max_results=max_results, year_from=year_from, year_to=year_to
        )

    async def _search_core(self, query: str, max_results: int) -> list[Paper]:
        return await self._core.search(query, max_results=max_results)

    async def _lookup_by_type(self, id_type: IDType, id_value: str) -> Paper | None:
        """Look up paper using the most appropriate API for the ID type."""
        if id_type == IDType.DOI:
            # Try S2 first (fast), fall back to OpenAlex, then CrossRef
            paper = await self._s2.lookup(f"DOI:{id_value}")
            if not paper:
                paper = await self._openalex.lookup_doi(id_value)
            if not paper:
                paper = await self._crossref.lookup_doi(id_value)
            return paper

        if id_type == IDType.PMID:
            paper = await self._pubmed.lookup_pmid(id_value)
            if not paper:
                paper = await self._s2.lookup(f"PMID:{id_value}")
            return paper

        if id_type == IDType.PMCID:
            paper = await self._openalex.lookup_pmcid(id_value)
            if not paper:
                paper = await self._s2.lookup(f"PMCID:{id_value}")
            return paper

        if id_type == IDType.ARXIV:
            # Try arXiv directly first (authoritative), then S2 as fallback
            paper = await self._arxiv.lookup_arxiv_id(id_value)
            if not paper:
                paper = await self._s2.lookup(f"ARXIV:{id_value}")
            return paper

        if id_type == IDType.S2:
            return await self._s2.lookup(id_value)

        if id_type == IDType.OPENALEX:
            # OpenAlex IDs are looked up via DOI endpoint workaround
            return await self._openalex.lookup_doi(id_value)

        return None

    async def _enrich(self, paper: Paper) -> Paper:
        """Enrich a paper with data from all available APIs."""
        from opencite.dedup import merge_papers

        tasks: list[asyncio.Task[Paper | None]] = []

        # Look up from other sources using available IDs
        if paper.doi:
            if "openalex" not in paper.data_sources:
                tasks.append(asyncio.create_task(self._openalex.lookup_doi(paper.doi)))
            if "s2" not in paper.data_sources:
                tasks.append(asyncio.create_task(self._s2.lookup(f"DOI:{paper.doi}")))
            if "pubmed" not in paper.data_sources:
                tasks.append(asyncio.create_task(self._pubmed.lookup_doi(paper.doi)))
            # For bioRxiv/medRxiv preprints, enrich from their Content APIs.
            # Both share the 10.1101 DOI prefix; fan out in parallel and the
            # one that hosts the preprint will return; the other returns None.
            if (
                paper.doi.startswith("10.1101/")
                and "biorxiv" not in paper.data_sources
                and "medrxiv" not in paper.data_sources
            ):
                tasks.append(asyncio.create_task(self._biorxiv.lookup_doi(paper.doi)))
                tasks.append(asyncio.create_task(self._medrxiv.lookup_doi(paper.doi)))
            # For arXiv DOIs, enrich from the arXiv API directly.
            if (
                paper.doi.lower().startswith("10.48550/arxiv.")
                and "arxiv" not in paper.data_sources
            ):
                tasks.append(asyncio.create_task(self._arxiv.lookup_doi(paper.doi)))
            # OSF Preprints (multi-prefix coverage: PsyArXiv, SocArXiv, ...).
            if OSFClient.is_osf_doi(paper.doi) and not any(
                s == "osf" or s.startswith("osf:") for s in paper.data_sources
            ):
                tasks.append(asyncio.create_task(self._osf.lookup_doi(paper.doi)))
            # Zenodo
            if (
                paper.doi.lower().startswith("10.5281/zenodo.")
                and "zenodo" not in paper.data_sources
            ):
                tasks.append(asyncio.create_task(self._zenodo.lookup_doi(paper.doi)))
            # Figshare
            if (
                paper.doi.lower().startswith("10.6084/m9.figshare.")
                and "figshare" not in paper.data_sources
            ):
                tasks.append(asyncio.create_task(self._figshare.lookup_doi(paper.doi)))
        elif paper.pmid:
            if "openalex" not in paper.data_sources:
                tasks.append(
                    asyncio.create_task(self._openalex.lookup_pmid(paper.pmid))
                )
            if "s2" not in paper.data_sources:
                tasks.append(asyncio.create_task(self._s2.lookup(f"PMID:{paper.pmid}")))
            if "pubmed" not in paper.data_sources:
                tasks.append(asyncio.create_task(self._pubmed.lookup_pmid(paper.pmid)))

        if not tasks:
            return paper

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Paper):
                paper = merge_papers(paper, r)

        return paper


def _sort_papers(papers: list[Paper], sort: str) -> list[Paper]:
    """Sort papers by the requested criterion."""
    if sort == "citations":
        return sorted(papers, key=lambda p: p.citation_count, reverse=True)
    if sort == "year":
        return sorted(
            papers,
            key=lambda p: (p.year or 0, p.citation_count),
            reverse=True,
        )
    # Default: relevance -- keep original order (relevance from APIs)
    return papers

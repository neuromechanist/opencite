"""Citation explorer for citation graph traversal and canonical paper discovery."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from opencite.clients.openalex import OpenAlexClient
from opencite.clients.semantic_scholar import SemanticScholarClient
from opencite.dedup import deduplicate
from opencite.models import CitationResult, IDType, Paper, parse_identifier

if TYPE_CHECKING:
    from opencite.config import Config

logger = logging.getLogger(__name__)


class CitationExplorer:
    """Explores citation graphs and finds canonical papers.

    Usage::

        async with CitationExplorer(config) as explorer:
            result = await explorer.citing_papers("10.1038/s41586-021-03819-2")
            for paper in result.papers:
                print(paper.title)
    """

    def __init__(self, config: Config):
        self.config = config
        self._openalex = OpenAlexClient(config)
        self._s2 = SemanticScholarClient(config)

    async def __aenter__(self) -> CitationExplorer:
        await self._openalex.__aenter__()
        await self._s2.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._openalex.__aexit__()
        await self._s2.__aexit__()

    async def citing_papers(
        self,
        identifier: str,
        max_results: int = 50,
        sort: str = "citations",
        min_citations: int = 0,
    ) -> CitationResult:
        """Find papers that cite the given paper."""
        id_type, id_value = parse_identifier(identifier)

        # Get the seed paper first
        seed = await self._lookup_seed(id_type, id_value)
        if seed is None:
            return CitationResult(
                seed_paper=Paper(title="Unknown", ids=_make_ids(id_type, id_value)),
                papers=[],
                direction="citing",
            )

        # Get citing papers from available sources
        tasks: list[asyncio.Task[list[Paper]]] = []

        if seed.ids.openalex_id:
            tasks.append(asyncio.create_task(
                self._openalex.citing_papers(seed.ids.openalex_id, max_results=max_results, sort=sort)
            ))
        if seed.ids.s2_id:
            tasks.append(asyncio.create_task(
                self._s2.citing_papers(seed.ids.s2_id, max_results=max_results)
            ))
        elif seed.doi:
            tasks.append(asyncio.create_task(
                self._s2.citing_papers(f"DOI:{seed.doi}", max_results=max_results)
            ))

        all_papers = await _gather_papers(tasks)

        # Deduplicate and filter
        unique = deduplicate(all_papers)
        if min_citations > 0:
            unique = [p for p in unique if p.citation_count >= min_citations]

        # Sort
        unique = _sort_papers(unique, sort)
        unique = unique[:max_results]

        return CitationResult(
            seed_paper=seed,
            papers=unique,
            direction="citing",
            total_available=len(all_papers),
        )

    async def references(
        self,
        identifier: str,
        max_results: int = 50,
    ) -> CitationResult:
        """Find papers referenced by the given paper."""
        id_type, id_value = parse_identifier(identifier)
        seed = await self._lookup_seed(id_type, id_value)
        if seed is None:
            return CitationResult(
                seed_paper=Paper(title="Unknown", ids=_make_ids(id_type, id_value)),
                papers=[],
                direction="references",
            )

        tasks: list[asyncio.Task[list[Paper]]] = []

        if seed.ids.openalex_id:
            tasks.append(asyncio.create_task(
                self._openalex.references(seed.ids.openalex_id, max_results=max_results)
            ))
        if seed.ids.s2_id:
            tasks.append(asyncio.create_task(
                self._s2.references(seed.ids.s2_id, max_results=max_results)
            ))
        elif seed.doi:
            tasks.append(asyncio.create_task(
                self._s2.references(f"DOI:{seed.doi}", max_results=max_results)
            ))

        all_papers = await _gather_papers(tasks)
        unique = deduplicate(all_papers)
        unique = unique[:max_results]

        return CitationResult(
            seed_paper=seed,
            papers=unique,
            direction="references",
            total_available=len(all_papers),
        )

    async def canonical_papers(
        self,
        query: str,
        max_results: int = 10,
        year_from: int | None = None,
        min_citations: int = 100,
    ) -> list[Paper]:
        """Find the most-cited papers in a field.

        Uses OpenAlex sorted by citation count descending.
        """
        papers = await self._openalex.canonical_search(
            query,
            max_results=max_results,
            year_from=year_from,
            min_citations=min_citations,
        )
        return papers

    async def _lookup_seed(self, id_type: IDType, id_value: str) -> Paper | None:
        """Look up the seed paper to get IDs for citation queries."""
        if id_type == IDType.DOI:
            # Try S2 first for fast lookup + S2 ID
            paper = await self._s2.lookup(f"DOI:{id_value}")
            if paper:
                # Also get OpenAlex ID
                oa_paper = await self._openalex.lookup_doi(id_value)
                if oa_paper:
                    from opencite.dedup import merge_papers
                    paper = merge_papers(paper, oa_paper)
                return paper
            return await self._openalex.lookup_doi(id_value)

        if id_type == IDType.PMID:
            paper = await self._s2.lookup(f"PMID:{id_value}")
            if paper and paper.doi:
                oa_paper = await self._openalex.lookup_doi(paper.doi)
                if oa_paper:
                    from opencite.dedup import merge_papers
                    paper = merge_papers(paper, oa_paper)
            return paper

        if id_type == IDType.ARXIV:
            return await self._s2.lookup(f"ARXIV:{id_value}")

        if id_type == IDType.S2:
            return await self._s2.lookup(id_value)

        if id_type == IDType.OPENALEX:
            return await self._openalex.lookup_doi(id_value)

        return None


def _make_ids(id_type: IDType, id_value: str) -> object:
    """Create an IDSet with the given ID type populated."""
    from opencite.models import IDSet
    kwargs = {
        IDType.DOI: "doi",
        IDType.PMID: "pmid",
        IDType.PMCID: "pmcid",
        IDType.OPENALEX: "openalex_id",
        IDType.S2: "s2_id",
        IDType.ARXIV: "arxiv_id",
    }
    field_name = kwargs.get(id_type, "doi")
    return IDSet(**{field_name: id_value})


async def _gather_papers(tasks: list[asyncio.Task[list[Paper]]]) -> list[Paper]:
    """Gather results from multiple tasks, ignoring failures."""
    all_papers: list[Paper] = []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_papers.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Citation query failed: %s", r)
    return all_papers


def _sort_papers(papers: list[Paper], sort: str) -> list[Paper]:
    """Sort papers by the requested criterion."""
    if sort == "citations":
        return sorted(papers, key=lambda p: p.citation_count, reverse=True)
    if sort == "year":
        return sorted(papers, key=lambda p: (p.year or 0, p.citation_count), reverse=True)
    return papers

"""Tests for the search orchestrator."""

from __future__ import annotations

import pytest

from opencite.config import Config
from opencite.models import Paper
from opencite.search import ALL_SOURCES, SearchOrchestrator, _sort_papers
from tests.conftest import skip_without_all_keys


def test_all_sources_includes_preprint_servers():
    """Preprint servers are first-class entries in ALL_SOURCES."""
    for src in (
        "arxiv",
        "biorxiv",
        "medrxiv",
        "osf",
        "zenodo",
        "figshare",
    ):
        assert src in ALL_SOURCES


@pytest.fixture
def config() -> Config:
    return Config.from_env()


# -- Unit tests for _sort_papers (no API needed) --


class TestSortPapers:
    def test_sort_by_citations(self):
        papers = [
            Paper(title="Low", citation_count=10),
            Paper(title="High", citation_count=1000),
            Paper(title="Mid", citation_count=100),
        ]
        sorted_papers = _sort_papers(papers, "citations")
        assert [p.title for p in sorted_papers] == ["High", "Mid", "Low"]

    def test_sort_by_year(self):
        papers = [
            Paper(title="Old", year=2000, citation_count=50),
            Paper(title="New", year=2024, citation_count=10),
            Paper(title="Mid", year=2015, citation_count=100),
        ]
        sorted_papers = _sort_papers(papers, "year")
        assert [p.title for p in sorted_papers] == ["New", "Mid", "Old"]

    def test_sort_relevance_preserves_order(self):
        papers = [Paper(title="A"), Paper(title="B"), Paper(title="C")]
        sorted_papers = _sort_papers(papers, "relevance")
        assert [p.title for p in sorted_papers] == ["A", "B", "C"]

    def test_empty_list(self):
        assert _sort_papers([], "citations") == []

    def test_none_year_handled(self):
        papers = [
            Paper(title="No Year"),
            Paper(title="Has Year", year=2020),
        ]
        sorted_papers = _sort_papers(papers, "year")
        assert sorted_papers[0].title == "Has Year"


@pytest.mark.integration
@skip_without_all_keys
class TestSearchOrchestrator:
    async def test_search_all_sources(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search("deep learning fMRI", max_results=10)
        assert len(result.papers) > 0
        assert result.deduplicated_count >= 0
        # Should have results from at least 2 sources
        all_sources = set()
        for p in result.papers:
            all_sources.update(p.data_sources)
        assert len(all_sources) >= 2

    async def test_search_single_source(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "CRISPR",
                max_results=5,
                sources=["openalex"],
            )
        assert len(result.papers) > 0
        for p in result.papers:
            assert "openalex" in p.data_sources

    async def test_search_deduplicates(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search("attention is all you need", max_results=10)
        # Papers should be deduplicated across sources
        assert result.deduplicated_count >= 0

    async def test_search_sort_by_citations(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "transformer",
                max_results=5,
                sort="citations",
            )
        assert len(result.papers) > 0
        # Check citation counts are in descending order
        counts = [p.citation_count for p in result.papers]
        assert counts == sorted(counts, reverse=True)

    async def test_lookup_doi(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.1038/s41586-021-03819-2")
        assert paper is not None
        assert paper.title
        assert paper.ids.doi == "10.1038/s41586-021-03819-2"

    async def test_lookup_pmid(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("pmid:34265844")
        assert paper is not None
        assert paper.ids.pmid == "34265844"

    async def test_lookup_with_enrich(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.1038/s41586-021-03819-2", enrich=True)
        assert paper is not None
        # Should have data from multiple sources
        assert len(paper.data_sources) >= 2

    async def test_lookup_not_found(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            paper = await searcher.lookup("10.9999/does-not-exist-xyz-abc")
        assert paper is None

    async def test_batch_lookup(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            papers = await searcher.batch_lookup(
                [
                    "10.1038/s41586-021-03819-2",
                    "pmid:34265844",
                ]
            )
        assert len(papers) >= 1

    async def test_source_counts(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "brain computer interface",
                max_results=5,
            )
        assert "openalex" in result.total_by_source
        assert "s2" in result.total_by_source
        assert "pubmed" in result.total_by_source

    async def test_search_with_year_filter(self, config: Config):
        async with SearchOrchestrator(config) as searcher:
            result = await searcher.search(
                "neural network",
                max_results=5,
                year_from=2022,
                year_to=2024,
            )
        assert len(result.papers) > 0


class TestEnrichPreprintBranches:
    """Unit tests for the new Phase 3 DOI-prefix branches in `_enrich`.

    These don't hit the network: each preprint client's `lookup_doi` is
    replaced with a stub that records calls. We assert the orchestrator
    schedules a lookup for the right client based on DOI prefix and the
    existing `data_sources` attribution guard.
    """

    @pytest.fixture
    def orchestrator(self):
        from unittest.mock import AsyncMock

        from opencite.search import SearchOrchestrator

        orch = SearchOrchestrator(Config())
        for client_attr in (
            "_openalex",
            "_s2",
            "_pubmed",
            "_arxiv",
            "_biorxiv",
            "_medrxiv",
            "_osf",
            "_zenodo",
            "_figshare",
            "_crossref",
            "_core",
        ):
            client = getattr(orch, client_attr)
            client.lookup_doi = AsyncMock(return_value=None)
            if hasattr(client, "lookup"):
                client.lookup = AsyncMock(return_value=None)
            if hasattr(client, "lookup_pmid"):
                client.lookup_pmid = AsyncMock(return_value=None)
        return orch

    @pytest.mark.asyncio
    async def test_osf_doi_triggers_osf_lookup(self, orchestrator):
        from opencite.models import IDSet

        paper = Paper(title="x", ids=IDSet(doi="10.31234/osf.io/abc12"))
        await orchestrator._enrich(paper)
        orchestrator._osf.lookup_doi.assert_called_once_with("10.31234/osf.io/abc12")

    @pytest.mark.asyncio
    async def test_osf_skipped_when_already_attributed(self, orchestrator):
        from opencite.models import IDSet

        paper = Paper(
            title="x",
            ids=IDSet(doi="10.31234/osf.io/abc12"),
            data_sources={"osf:psyarxiv"},
        )
        await orchestrator._enrich(paper)
        orchestrator._osf.lookup_doi.assert_not_called()

    @pytest.mark.asyncio
    async def test_zenodo_doi_triggers_zenodo_lookup(self, orchestrator):
        from opencite.models import IDSet

        paper = Paper(title="x", ids=IDSet(doi="10.5281/zenodo.123456"))
        await orchestrator._enrich(paper)
        orchestrator._zenodo.lookup_doi.assert_called_once_with("10.5281/zenodo.123456")

    @pytest.mark.asyncio
    async def test_figshare_doi_triggers_figshare_lookup(self, orchestrator):
        from opencite.models import IDSet

        paper = Paper(title="x", ids=IDSet(doi="10.6084/m9.figshare.999"))
        await orchestrator._enrich(paper)
        orchestrator._figshare.lookup_doi.assert_called_once_with(
            "10.6084/m9.figshare.999"
        )

    @pytest.mark.asyncio
    async def test_unrelated_doi_does_not_trigger_preprint_clients(self, orchestrator):
        from opencite.models import IDSet

        paper = Paper(title="x", ids=IDSet(doi="10.1038/nature12373"))
        await orchestrator._enrich(paper)
        orchestrator._osf.lookup_doi.assert_not_called()
        orchestrator._zenodo.lookup_doi.assert_not_called()
        orchestrator._figshare.lookup_doi.assert_not_called()
